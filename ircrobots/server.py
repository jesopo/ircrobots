import asyncio
from ssl         import SSLContext
from asyncio     import Future, PriorityQueue, Queue
from typing      import List, Optional, Set, Tuple

from asyncio_throttle import Throttler
from ircstates        import Emit
from irctokens        import build, Line, tokenise

from .ircv3     import CAPContext, CAP_SASL
from .interface import (ConnectionParams, ICapability, IServer, SentLine,
    SendPriority, SASLParams, IMatchResponse)
from .sasl      import SASLContext, SASLResult
from .security  import ssl_context

THROTTLE_RATE = 4 # lines
THROTTLE_TIME = 2 # seconds

class Server(IServer):
    _reader: asyncio.StreamReader
    _writer: asyncio.StreamWriter
    params:  ConnectionParams

    def __init__(self, name: str):
        super().__init__(name)

        self.throttle = Throttler(
            rate_limit=100, period=THROTTLE_TIME)

        self.sasl_state = SASLResult.NONE

        self._wait_for_cache: List[Tuple[Line, List[Emit]]] = []
        self._write_queue:    PriorityQueue[SentLine] = PriorityQueue()
        self._read_queue:     Queue[Tuple[Line, List[Emit]]] = Queue()
        self.desired_caps:    Set[ICapability] = set([])

    async def send_raw(self, line: str, priority=SendPriority.DEFAULT
            ) -> Future:
        return await self.send(tokenise(line), priority)
    async def send(self, line: Line, priority=SendPriority.DEFAULT) -> Future:
        prio_line = SentLine(priority, line)
        await self._write_queue.put(prio_line)
        prio_line.future

    def set_throttle(self, rate: int, time: float):
        self.throttle.rate_limit = rate
        self.throttle.period     = time

    async def connect(self, params: ConnectionParams):
        cur_ssl: Optional[SSLContext] = None
        if params.tls:
            cur_ssl = ssl_context(params.tls_verify)

        reader, writer = await asyncio.open_connection(
            params.host,
            params.port,
            ssl=cur_ssl,
            local_addr=(params.bindhost, 0))

        self._reader = reader
        self._writer = writer
        self.params = params

    async def handshake(self):
        nickname = self.params.nickname
        username = self.params.username or nickname
        realname = self.params.realname or nickname

        await self.send(build("CAP",  ["LS", "302"]))
        await self.send(build("NICK", [nickname]))
        await self.send(build("USER", [username, "0", "*", realname]))

        await CAPContext(self).handshake()

    async def _on_read_emit(self, line: Line, emit: Emit):
        if emit.command   == "001":
            self.set_throttle(THROTTLE_RATE, THROTTLE_TIME)
        elif emit.command   == "CAP":
            if emit.subcommand == "NEW":
                await self._cap_new(emit)
        elif emit.command == "JOIN":
            if emit.self and not emit.channel is None:
                await self.send(build("MODE", [emit.channel.name]))

    async def _on_read_line(self, line: Line):
        if line.command == "PING":
            await self.send(build("PONG", line.params))

    async def line_read(self, line: Line):
        pass
    async def _read_lines(self) -> List[Tuple[Line, List[Emit]]]:
        data = await self._reader.read(1024)
        lines = self.recv(data)
        for line, emits in lines:
            for emit in emits:
                await self._on_read_emit(line, emit)

            await self._on_read_line(line)
            await self.line_read(line)

            await self._read_queue.put((line, emits))
        return lines
    async def next_line(self) -> Line:
        line, emits = await self._read_queue.get()
        return line

    async def wait_for(self, response: IMatchResponse) -> Line:
        while True:
            lines = self._wait_for_cache.copy()
            self._wait_for_cache.clear()

            if not lines:
                lines += await self._read_lines()

            for i, (line, emits) in enumerate(lines):
                if response.match(self, line):
                    self._wait_for_cache = lines[i+1:]
                    return line

    async def line_send(self, line: Line):
        pass
    async def _write_lines(self) -> List[Line]:
        lines: List[SentLine] = []

        while (not lines or
                (len(lines) < 5 and self._write_queue.qsize() > 0)):
            prio_line = await self._write_queue.get()
            lines.append(prio_line)

        for line in lines:
            async with self.throttle:
                self._writer.write(
                    f"{line.line.format()}\r\n".encode("utf8"))

        await self._writer.drain()

        for line in lines:
            line.future.set_result(None)

        return [l.line for l in lines]

    # CAP-related
    def cap_agreed(self, capability: ICapability) -> bool:
        return bool(self.cap_available(capability))
    def cap_available(self, capability: ICapability) -> Optional[str]:
        return capability.available(self.agreed_caps)

    async def _cap_new(self, emit: Emit):
        if not emit.tokens is None:
            tokens = [t.split("=", 1)[0] for t in emit.tokens]
            if CAP_SASL.available(tokens) and not self.params.sasl is None:
                await self.sasl_auth(self.params.sasl)

    async def sasl_auth(self, params: SASLParams) -> bool:
        if (self.sasl_state == SASLResult.NONE and
                self.cap_agreed(CAP_SASL)):

            res = await SASLContext(self).from_params(params)
            self.sasl_state = res
            return True
        else:
            return False
    # /CAP-related
