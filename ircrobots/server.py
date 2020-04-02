import asyncio
from ssl         import SSLContext
from asyncio     import Future, PriorityQueue
from typing      import Awaitable, List, Optional, Set, Tuple

from asyncio_throttle import Throttler
from ircstates        import Emit
from irctokens        import build, Line, tokenise

from .ircv3     import CAPContext, CAPS, CAP_SASL
from .interface import (ConnectionParams, ICapability, IServer, PriorityLine,
    SendPriority)
from .matching  import BaseResponse
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
            rate_limit=THROTTLE_RATE, period=THROTTLE_TIME)
        self.sasl_state = SASLResult.NONE

        self._write_queue: PriorityQueue[PriorityLine] = PriorityQueue()
        self._cap_queue:   Set[ICapability] = set([])

        self._wait_for: List[Tuple[BaseResponse, Future]] = []

    async def send_raw(self, line: str, priority=SendPriority.DEFAULT):
        await self.send(tokenise(line), priority)
    async def send(self, line: Line, priority=SendPriority.DEFAULT):
        await self._write_queue.put(PriorityLine(priority, line))

    def set_throttle(self, rate: int, time: float):
        self.throttle.rate_limit = rate
        self.throttle.period     = time

    async def connect(self, params: ConnectionParams):
        cur_ssl: Optional[SSLContext] = None
        if params.ssl:
            cur_ssl = ssl_context(params.ssl_verify)

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
        if emit.command   == "CAP":
            if emit.subcommand == "NEW":
                await self._cap_new(emit)
        elif emit.command == "JOIN":
            if emit.self:
                await self.send(build("MODE", [emit.channel.name]))

    async def _on_read_line(self, line: Line):
        for i, (response, future) in enumerate(self._wait_for):
            if response.match(line):
                self._wait_for.pop(i)
                future.set_result(line)
                break

        if line.command == "PING":
            await self.send(build("PONG", line.params))

    async def _read_lines(self) -> List[Tuple[Line, List[Emit]]]:
        data = await self._reader.read(1024)
        lines = self.recv(data)
        return lines

    def wait_for(self, response: BaseResponse) -> Awaitable[Line]:
        future: "Future[Line]" = asyncio.Future()
        self._wait_for.append((response, future))
        return future

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

    # CAP-related
    async def queue_capability(self, cap: ICapability):
        self._cap_queue.add(cap)

    def cap_agreed(self, capability: ICapability) -> bool:
        return bool(self.cap_available(capability))
    def cap_available(self, capability: ICapability) -> Optional[str]:
        return capability.available(self.agreed_caps)

    def collect_caps(self) -> List[str]:
        caps = CAPS+list(self._cap_queue)
        self._cap_queue.clear()

        if not self.params.sasl is None:
            caps.append(CAP_SASL)

        matched = [c.available(self.available_caps) for c in caps]
        return [name for name in matched if not name is None]

    async def _cap_new(self, emit: Emit):
        if not emit.tokens is None:
            tokens = [t.split("=", 1)[0] for t in emit.tokens]
            if CAP_SASL.available(tokens):
                await self.maybe_sasl()

    async def maybe_sasl(self) -> bool:
        if (self.sasl_state == SASLResult.NONE and
                not self.params.sasl is None and
                self.cap_agreed(CAP_SASL)):
            res = await SASLContext(self).from_params(self.params.sasl)
            self.sasl_state = res
            return True
        else:
            return False

    # /CAP-related
