import asyncio
from asyncio     import Future, PriorityQueue
from typing      import Awaitable, Deque, Dict, List, Optional, Set, Tuple
from collections import deque
from time        import monotonic

from asyncio_throttle   import Throttler
from async_timeout      import timeout
from ircstates          import Emit, Channel
from ircstates.numerics import *
from ircstates.server   import ServerDisconnectedException
from irctokens          import build, Line, tokenise

from .ircv3     import (CAPContext, sts_transmute, CAP_ECHO, CAP_SASL,
    CAP_LABEL, LABEL_TAG, resume_transmute)
from .sasl      import SASLContext, SASLResult
from .join_info import WHOContext
from .matching  import ResponseOr, Responses, Response, ANY, Folded, Nickname
from .asyncs    import MaybeAwait, WaitFor
from .struct    import Whois
from .params    import ConnectionParams, SASLParams, STSPolicy, ResumePolicy
from .interface import (IBot, ICapability, IServer, SentLine, SendPriority,
    IMatchResponse)
from .interface import ITCPTransport, ITCPReader, ITCPWriter

THROTTLE_RATE = 4 # lines
THROTTLE_TIME = 2 # seconds
PING_TIMEOUT  = 60 # seconds

class Server(IServer):
    _reader: ITCPReader
    _writer: ITCPWriter
    params:  ConnectionParams

    def __init__(self, bot: IBot, name: str):
        super().__init__(name)
        self.bot = bot

        self.disconnected = False

        self.throttle = Throttler(
            rate_limit=100, period=THROTTLE_TIME)

        self.sasl_state = SASLResult.NONE
        self.last_read  = -1.0
        self._ping_sent = False

        self._sent_count:  int = 0
        self._write_queue: PriorityQueue[SentLine] = PriorityQueue()
        self.desired_caps: Set[ICapability] = set([])

        self._read_queue:  Deque[Tuple[Line, Optional[Emit]]] = deque()

        self._wait_for:     List[Tuple[Awaitable, WaitFor]] = []
        self._wait_for_fut: Optional[Future[WaitFor]] = None

    def hostmask(self) -> str:
        hostmask = self.nickname
        if not self.username is None:
            hostmask += f"!{self.username}"
        if not self.hostname is None:
            hostmask += f"@{self.hostname}"
        return hostmask

    def send_raw(self, line: str, priority=SendPriority.DEFAULT
            ) -> Awaitable[SentLine]:
        return self.send(tokenise(line), priority)
    def send(self, line: Line, priority=SendPriority.DEFAULT
            ) -> Awaitable[SentLine]:
        sent_line = SentLine(self._sent_count, priority, line)
        self._sent_count += 1

        label = self.cap_available(CAP_LABEL)
        if not label is None:
            tag = LABEL_TAG[label]
            if line.tags is None or not tag in line.tags:
                if line.tags is None:
                    line.tags = {}
                line.tags[tag] = str(sent_line.id)

        self._write_queue.put_nowait(sent_line)

        async def _assure() -> SentLine:
            await sent_line.future
            return sent_line
        return MaybeAwait(_assure)

    def set_throttle(self, rate: int, time: float):
        self.throttle.rate_limit = rate
        self.throttle.period     = time

    def server_address(self) -> Tuple[str, int]:
        return self._writer.get_peer()

    async def connect(self,
            transport: ITCPTransport,
            params: ConnectionParams):
        await sts_transmute(params)
        await resume_transmute(params)

        reader, writer = await transport.connect(
            params.host,
            params.port,
            tls       =params.tls,
            tls_verify=params.tls_verify,
            bindhost  =params.bindhost)

        self._reader = reader
        self._writer = writer

        self.params = params
        await self.handshake()
    async def disconnect(self):
        if not self._writer is None:
            await self._writer.close()
            self._writer = None
            self._read_queue.clear()

    async def handshake(self):
        nickname = self.params.nickname
        username = self.params.username or nickname
        realname = self.params.realname or nickname

        # these must remain non-awaited; reading hasn't started yet
        if not self.params.password is None:
            self.send(build("PASS", [self.params.password]))
        self.send(build("CAP",  ["LS", "302"]))
        self.send(build("NICK", [nickname]))
        self.send(build("USER", [username, "0", "*", realname]))

    # to be overridden
    async def line_read(self, line: Line):
        pass
    async def line_send(self, line: Line):
        pass
    async def sts_policy(self, sts: STSPolicy):
        pass
    async def resume_policy(self, resume: ResumePolicy):
        pass
    # /to be overriden

    async def _on_read_emit(self, line: Line, emit: Emit):
        if emit.command == "001":
            await self.send(build("WHO", [self.nickname]))
            self.set_throttle(THROTTLE_RATE, THROTTLE_TIME)

        elif emit.command == "CAP":
            if emit.subcommand    == "NEW":
                await self._cap_ls(emit)
            elif (emit.subcommand == "LS" and
                    emit.finished):
                if not self.registered:
                    await CAPContext(self).handshake()
                else:
                    await self._cap_ls(emit)

        elif emit.command == "JOIN":
            if emit.self and not emit.channel is None:
                await self.send(build("MODE", [emit.channel.name]))
                await WHOContext(self).ensure(emit.channel.name)

    async def _on_read_line(self, line: Line):
        if line.command == "PING":
            await self.send(build("PONG", line.params))

    async def _line_or_wait(self, line_aw: Awaitable):
        wait_for_fut: Future[WaitFor] = Future()
        self._wait_for_fut = wait_for_fut

        done, pend = await asyncio.wait([line_aw, wait_for_fut],
            return_when=asyncio.FIRST_COMPLETED)

        if wait_for_fut.done():
            new_line_aw = list(pend)[0]
            self._wait_for.append((new_line_aw, await wait_for_fut))

    async def next_line(self) -> Tuple[Line, Optional[Emit]]:
        if self._read_queue:
            both = self._read_queue.popleft()
        else:
            while True:

                try:
                    async with timeout(PING_TIMEOUT):
                        data = await self._reader.read(1024)
                except asyncio.exceptions.TimeoutError:
                    if self._ping_sent:
                        data = b"" # empty data means the socket disconnected
                    else:
                        self._ping_sent = True
                        await self.send(build("PING", ["hello"]))
                        continue

                self.last_read  = monotonic()
                self._ping_sent = False

                try:
                    lines = self.recv(data)
                except ServerDisconnectedException:
                    self.disconnected = True
                    raise

                if lines:
                    self._read_queue.extend(lines[1:])
                    both = lines[0]
                    break

        line, emit = both
        async def _line():
            if emit is not None:
                await self._on_read_emit(line, emit)
            await self._on_read_line(line)
            await self.line_read(line)

        for i, (aw, wait_for) in enumerate(self._wait_for):
            if wait_for.response.match(self, line):
                wait_for.resolve(line)
                self._wait_for.pop(i)
                await self._line_or_wait(aw)
                break

        await self._line_or_wait(_line())

        return both

    async def wait_for(self, response: IMatchResponse) -> Line:
        wait_for_fut = self._wait_for_fut
        if wait_for_fut is not None:
            self._wait_for_fut = None

            our_wait_for = WaitFor(response)
            wait_for_fut.set_result(our_wait_for)
            return await our_wait_for
        raise Exception()

    async def _on_write_line(self, line: Line):
        if (line.command == "PRIVMSG" and
                not self.cap_agreed(CAP_ECHO)):
            new_line = line.with_source(self.hostmask())
            emit = self.parse_tokens(new_line)
            self._read_queue.append((new_line, emit))

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
            await self._on_write_line(line.line)
            await self.line_send(line.line)
            line.future.set_result(line)

        return [l.line for l in lines]

    # CAP-related
    def cap_agreed(self, capability: ICapability) -> bool:
        return bool(self.cap_available(capability))
    def cap_available(self, capability: ICapability) -> Optional[str]:
        return capability.available(self.agreed_caps)

    async def _cap_ls(self, emit: Emit):
        if not emit.tokens is None:
            tokens: Dict[str, str] = {}
            for token in emit.tokens:
                key, _, value = token.partition("=")
                tokens[key] = value
            await CAPContext(self).on_ls(tokens)

    async def sasl_auth(self, params: SASLParams) -> bool:
        if (self.sasl_state == SASLResult.NONE and
                self.cap_agreed(CAP_SASL)):

            res = await SASLContext(self).from_params(params)
            self.sasl_state = res
            return True
        else:
            return False
    # /CAP-related

    def send_join(self,
            name: str,
            key: Optional[str]=None
            ) -> Awaitable[Channel]:
        fut = self.send_joins([name], [] if key is None else [key])

        async def _assure():
            channels = await fut
            return channels[0]
        return MaybeAwait(_assure)
    def send_part(self, name: str):
        fut = self.send(build("PART", [name]))

        async def _assure():
            line = await self.wait_for(Response(
                "PART",
                [ParamFolded(name)],
                source=Nickname(self.nickname_lower)
            ))
            return
        return MaybeAwait(_assure)

    def send_joins(self,
            names: List[str],
            keys:  List[str]=[]
            ) -> Awaitable[List[Channel]]:

        folded_names = [self.casefold(name) for name in names]

        if not keys:
            fut = self.send(build("JOIN", [",".join(names)]))
        else:
            fut = self.send(build("JOIN", [",".join(names)]+keys))

        async def _assure():
            await fut

            channels: List[Channel] = []

            while folded_names:
                line = await self.wait_for(
                    Response(RPL_CHANNELMODEIS, [ANY, ANY])
                )

                folded = self.casefold(line.params[1])
                if folded in folded_names:
                    folded_names.remove(folded)
                    channels.append(self.channels[folded])

            return channels
        return MaybeAwait(_assure)

    def send_whois(self, target: str) -> Awaitable[Whois]:
        folded = self.casefold(target)
        fut = self.send(build("WHOIS", [target, target]))

        async def _assure():
            await fut
            params = [ANY, Folded(folded)]
            obj = Whois()
            while True:
                line = await self.wait_for(Responses([
                    RPL_WHOISUSER,
                    RPL_WHOISSERVER,
                    RPL_WHOISOPERATOR,
                    RPL_WHOISIDLE,
                    RPL_WHOISHOST,
                    RPL_WHOISACCOUNT,
                    RPL_WHOISSECURE,
                    RPL_ENDOFWHOIS
                ], params))

                if line.command   == RPL_WHOISUSER:
                    obj.username, obj.hostname, _, obj.realname = line.params[2:]
                elif line.command == RPL_WHOISIDLE:
                    obj.idle, signon, _ = line.params[2:]
                    obj.signon = int(signon)
                elif line.command == RPL_WHOISACCOUNT:
                    obj.account = line.params[2]
                elif line.command == RPL_ENDOFWHOIS:
                    return obj
        return MaybeAwait(_assure)
