import asyncio, ssl
from queue       import Queue
from typing      import Callable, Dict, List, Optional, Tuple
from enum        import Enum
from dataclasses import dataclass

from asyncio_throttle import Throttler
from ircstates        import Server as BaseServer
from irctokens        import build, Line, tokenise

sc = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

THROTTLE_RATE = 4 # lines
THROTTLE_TIME = 2 # seconds

@dataclass
class ConnectionParams(object):
    nickname: str
    host:     str
    port:     int
    ssl:      bool

    username: Optional[str] = None
    realname: Optional[str] = None
    bindhost: Optional[str] = None

class SendPriority(Enum):
    HIGH   = 0
    MEDIUM = 10
    LOW    = 20

    DEFAULT = MEDIUM

class Server(BaseServer):
    _reader: asyncio.StreamReader
    _writer: asyncio.StreamWriter
    params:  ConnectionParams

    def __init__(self, name: str):
        super().__init__(name)
        self.throttle = Throttler(
            rate_limit=THROTTLE_RATE, period=THROTTLE_TIME)
        self._write_queue: asyncio.PriorityQueue[Tuple[int, Line]] = asyncio.PriorityQueue()

    async def send_raw(self, line: str, priority=SendPriority.DEFAULT):
        await self.send(tokenise(line), priority)
    async def send(self, line: Line, priority=SendPriority.DEFAULT):
        await self._write_queue.put((priority, line))

    def set_throttle(self, rate: int, time: float):
        self.throttle.rate_limit = rate
        self.throttle.period     = time

    async def connect(self, params: ConnectionParams):
        cur_ssl = sc if params.ssl else None
        reader, writer = await asyncio.open_connection(
            params.host, params.port, ssl=cur_ssl)
        self._reader = reader
        self._writer = writer

        nickname = params.nickname
        username = params.username or nickname
        realname = params.realname or nickname

        await self.send(build("NICK", [nickname]))
        await self.send(build("USER", [username, "0", "*", realname]))

        self.params = params

    async def line_received(self, line: Line):
        pass
    async def _read_lines(self) -> List[Line]:
        data = await self._reader.read(1024)
        lines = self.recv(data)
        for line in lines:
            print(f"{self.name}< {line.format()}")
            await self.line_received(line)
        return lines

    async def line_written(self, line: Line):
        pass
    async def _write_lines(self) -> List[Line]:
        lines: List[Line] = []

        while (not lines or
                (len(lines) < 5 and self._write_queue.qsize() > 0)):
            prio, line = await self._write_queue.get()
            lines.append(line)

        for line in lines:
            async with self.throttle:
                self._writer.write(f"{line.format()}\r\n".encode("utf8"))
        await self._writer.drain()
        return lines
