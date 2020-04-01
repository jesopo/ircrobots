import asyncio, ssl
from asyncio     import PriorityQueue
from queue       import Queue
from typing      import Callable, Dict, List, Optional, Set, Tuple
from enum        import IntEnum
from dataclasses import dataclass

from asyncio_throttle import Throttler
from ircstates        import Server as BaseServer
from ircstates        import Emit
from irctokens        import build, Line, tokenise

from .ircv3 import Capability, CAPS
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

class SendPriority(IntEnum):
    HIGH   = 0
    MEDIUM = 10
    LOW    = 20
    DEFAULT = MEDIUM

class PriorityLine(object):
    def __init__(self, priority: int, line: Line):
        self.priority = priority
        self.line = line
    def __lt__(self, other: "PriorityLine") -> bool:
        return self.priority < other.priority

class Server(BaseServer):
    _reader: asyncio.StreamReader
    _writer: asyncio.StreamWriter
    params:  ConnectionParams

    def __init__(self, name: str):
        super().__init__(name)

        self.throttle = Throttler(
            rate_limit=THROTTLE_RATE, period=THROTTLE_TIME)

        self._write_queue: PriorityQueue[PriorityLine] = PriorityQueue()

        self._cap_queue:      Set[Capability] = set([])
        self._requested_caps: List[str]       = []

    async def send_raw(self, line: str, priority=SendPriority.DEFAULT):
        await self.send(tokenise(line), priority)
    async def send(self, line: Line, priority=SendPriority.DEFAULT):
        await self._write_queue.put(PriorityLine(priority, line))

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

        await self.send(build("CAP",  ["LS"]))
        await self.send(build("NICK", [nickname]))
        await self.send(build("USER", [username, "0", "*", realname]))

        self.params = params

    async def queue_capability(self, cap: Capability):
        self._cap_queue.add(cap)
    async def _cap_ls_done(self):
        caps = CAPS+list(self._cap_queue)
        self._cap_queue.clear()

        matches = list(filter(bool,
            (c.available(self.available_caps) for c in caps)))
        if matches:
            self._requested_caps = matches
            await self.send(build("CAP", ["REQ", " ".join(matches)]))
    async def _cap_ack(self, line: Line):
        caps = line.params[2].split(" ")
        for cap in caps:
            if cap in self._requested_caps:
                self._requested_caps.remove(cap)
        if not self._requested_caps:
            await self.send(build("CAP", ["END"]))

    async def _on_read_emit(self, line: Line, emit: Emit):
        if emit.command == "CAP":
            if emit.subcommand == "LS" and emit.finished:
                await self._cap_ls_done()
            elif emit.subcommand in ["ACK", "NAK"]:
                await self._cap_ack(line)

    async def _on_read_line(self, line: Line):
        pass

    async def _read_lines(self) -> List[Tuple[Line, List[Emit]]]:
        data = await self._reader.read(1024)
        lines = self.recv(data)

        for line, emits in lines:
            for emit in emits:
                await self._on_read_emit(line, emit)
            await self._on_read_line(line)
        return lines

    async def line_written(self, line: Line):
        pass
    async def _write_lines(self) -> List[Line]:
        lines: List[Line] = []

        while (not lines or
                (len(lines) < 5 and self._write_queue.qsize() > 0)):
            prio_line = await self._write_queue.get()
            lines.append(prio_line.line)

        for line in lines:
            async with self.throttle:
                self._writer.write(f"{line.format()}\r\n".encode("utf8"))
        await self._writer.drain()
        return lines
