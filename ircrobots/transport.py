from ssl           import SSLContext
from typing        import Optional, Tuple
from asyncio       import StreamReader, StreamWriter
from async_stagger import open_connection

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

        local_addr: Optional[Tuple[str, int]] = None
        if not bindhost is None:
            local_addr = (bindhost, 53567)

        reader, writer = await open_connection(
            hostname,
            port,
            server_hostname=hostname,
            ssl            =cur_ssl,
            local_addr     =local_addr)
        return (TCPReader(reader), TCPWriter(writer))

