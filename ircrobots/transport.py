from ssl     import SSLContext
from typing  import Optional, Tuple
from asyncio import open_connection, StreamReader, StreamWriter

from .interface import ITCPTransport, ITCPReader, ITCPWriter
from .security  import tls_context

class TCPReader(ITCPReader):
    def __init__(self, reader: StreamReader):
        self._reader = reader

    async def read(self, byte_count: int) -> bytes:
        return await self._reader.read(byte_count)
class TCPWriter(ITCPWriter):
    def __init__(self, writer: StreamWriter):
        self._writer = writer

    def write(self, data: bytes):
        self._writer.write(data)

    async def drain(self):
        await self._writer.drain()

class TCPTransport(ITCPTransport):
    async def connect(self,
            hostname:   str,
            port:       int,
            tls:        bool,
            tls_verify: bool=True,
            bindhost:   Optional[str]=None
            ) -> Tuple[ITCPReader, ITCPWriter]:

        cur_ssl: Optional[SSLContext] = None
        if tls:
            cur_ssl = tls_context(tls_verify)

        reader, writer = await open_connection(
            hostname,
            port,
            ssl=cur_ssl,
            local_addr=(bindhost, 0))
        return (TCPReader(reader), TCPWriter(writer))
