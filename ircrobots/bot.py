import asyncio, traceback
import anyio
from typing import Dict

from ircstates.server import ServerDisconnectedException

from .server    import ConnectionParams, Server
from .transport import TCPTransport
from .interface import IBot, IServer

class Bot(IBot):
    def __init__(self):
        self.servers: Dict[str, Server] = {}
        self._server_queue: asyncio.Queue[Server] = asyncio.Queue()

    def create_server(self, name: str):
        return Server(self, name)

    async def disconnected(self, server: IServer):
        if (server.name in self.servers and
                server.params is not None and
                server.disconnected):

            reconnect = server.params.reconnect

            while True:
                await asyncio.sleep(reconnect)
                try:
                    await self.add_server(server.name, server.params)
                except Exception as e:
                    traceback.print_exc()
                    # let's try again, exponential backoff up to 5 mins
                    reconnect = min(reconnect*2, 300)
                else:
                    break

    async def disconnect(self, server: IServer):
        del self.servers[server.name]
        await server.disconnect()

    async def add_server(self, name: str, params: ConnectionParams) -> Server:
        server = self.create_server(name)
        self.servers[name] = server
        await server.connect(TCPTransport(), params)
        await self._server_queue.put(server)
        return server

    async def _run_server(self, server: Server):
        try:
            async with anyio.create_task_group() as tg:
                await tg.spawn(server._read_lines)
                await tg.spawn(server._send_lines)
        except ServerDisconnectedException:
            server.disconnected = True

        await self.disconnected(server)

    async def run(self):
        async with anyio.create_task_group() as tg:
            while not tg.cancel_scope.cancel_called:
                server = await self._server_queue.get()
                await tg.spawn(self._run_server, server)
