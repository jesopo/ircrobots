import asyncio
from asyncio     import Future, PriorityQueue
from typing      import (AsyncIterable, Awaitable, Deque, Dict, Iterable, List,
    Optional, Set, Tuple, Union)
from collections import deque
from time        import monotonic

import anyio
from asyncio_throttle   import Throttler
from async_timeout      import timeout
from ircstates          import Emit, Channel, ChannelUser
from ircstates.numerics import *
from ircstates.server   import ServerDisconnectedException
from ircstates.names    import Name
from irctokens          import build, Line, tokenise

from .ircv3     import (CAPContext, sts_transmute, CAP_ECHO, CAP_SASL,
    CAP_LABEL, LABEL_TAG_MAP, resume_transmute)
from .sasl      import SASLContext, SASLResult
from .matching  import (ResponseOr, Responses, Response, ANY, SELF, MASK_SELF,
    Folded)
from .asyncs    import MaybeAwait, WaitFor
from .struct    import Whois
from .params    import ConnectionParams, SASLParams, STSPolicy, ResumePolicy
from .interface import (IBot, ICapability, IServer, SentLine, SendPriority,
    IMatchResponse)
from .interface import ITCPTransport, ITCPReader, ITCPWriter

THROTTLE_RATE = 4  # lines
THROTTLE_TIME = 2  # seconds
PING_TIMEOUT  = 60 # seconds
WAIT_TIMEOUT  = 20 # seconds

JOIN_ERR_FIRST = [
    ERR_NOSUCHCHANNEL,
    ERR_BADCHANNAME,
    ERR_UNAVAILRESOURCE,
    ERR_TOOMANYCHANNELS,
    ERR_BANNEDFROMCHAN,
    ERR_INVITEONLYCHAN,
    ERR_BADCHANNELKEY,
    ERR_NEEDREGGEDNICK,
    ERR_THROTTLE
]

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

        self._sent_count:  int = 0
        self._send_queue: PriorityQueue[SentLine] = PriorityQueue()
        self.desired_caps: Set[ICapability] = set([])

        self._read_queue:  Deque[Tuple[Line, Optional[Emit]]] = deque()

        self._wait_fors: List[WaitFor] = []
        self._wait_for_fut: Dict[asyncio.Task, Future[bool]] = {}

        self._pending_who: Deque[str] = deque()

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
    def send(self,
            line: Line,
            priority=SendPriority.DEFAULT
            ) -> Awaitable[SentLine]:

        self.line_presend(line)
        sent_line = SentLine(self._sent_count, priority, line)
        self._sent_count += 1

        label = self.cap_available(CAP_LABEL)
        if not label is None:
            tag = LABEL_TAG_MAP[label]
            if line.tags is None or not tag in line.tags:
                if line.tags is None:
                    line.tags = {}
                line.tags[tag] = str(sent_line.id)

        self._send_queue.put_nowait(sent_line)

        return sent_line.future

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
    def line_preread(self, line: Line):
        pass
    def line_presend(self, line: Line):
        pass
    async def line_read(self, line: Line):
        pass
    async def line_send(self, line: Line):
        pass
    async def sts_policy(self, sts: STSPolicy):
        pass
    async def resume_policy(self, resume: ResumePolicy):
        pass
    # /to be overriden

    async def _on_read(self, line: Line, emit: Optional[Emit]):
        if line.command == "PING":
            await self.send(build("PONG", line.params))

        elif emit is not None:
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

                    self._pending_who.append(emit.channel.name)
                    if len(self._pending_who) == 1:
                        await self._serial_who()

        await self.line_read(line)

    async def _serial_who(self):
        while self._pending_who:
            next = self._pending_who.popleft()
            if self.isupport.whox:
                await self.send(self.prepare_whox(next))
            else:
                await self.send(build("WHO", [next]))

            end = Response(RPL_ENDOFWHO, [ANY, Folded(next)])
            line = await self.wait_for(end)


    async def _next_lines(self) -> AsyncIterable[Line]:
        ping_sent = False
        while True:
            try:
                async with timeout(PING_TIMEOUT):
                    data = await self._reader.read(1024)
            except asyncio.TimeoutError:
                if ping_sent:
                    data = b"" # empty data means the socket disconnected
                else:
                    ping_sent = True
                    await self.send(build("PING", ["hello"]))
                    continue

            self.last_read = monotonic()
            ping_sent      = False

            try:
                lines = self.recv(data)
            except ServerDisconnectedException:
                self.disconnected = True
                raise

            for line in lines:
                yield line

    async def _line_or_wait(self,
            line_aw: asyncio.Task
            ) -> Optional[Awaitable]:
        wait_for_fut: Future[bool] = Future()
        self._wait_for_fut[line_aw] = wait_for_fut

        done, pend = await asyncio.wait([line_aw, wait_for_fut],
            return_when=asyncio.FIRST_COMPLETED)
        del self._wait_for_fut[line_aw]

        if wait_for_fut.done():
            new_line_aw = list(pend)[0]
            return new_line_aw
        else:
            return None

    async def _read_lines(self) -> AsyncIterable[Tuple[Line, Optional[Emit]]]:
        async with anyio.create_task_group() as tg:
            async for line in self._next_lines():
                emit = self.parse_tokens(line)
                self.line_preread(line)

                for i, wait_for in enumerate(self._wait_fors):
                    if wait_for.match(self, line):
                        wait_for.resolve(line)
                        self._wait_fors.pop(i)
                        break

                line_aw = asyncio.create_task(self._on_read(line, emit))
                new_wait = await self._line_or_wait(line_aw)
                if new_wait is not None:
                    async def _aw():
                        await new_wait
                    await tg.spawn(_aw)

                yield (line, emit)

    async def wait_for(self,
            response: Union[IMatchResponse, Set[IMatchResponse]],
            sent_aw:  Optional[Awaitable[SentLine]]=None,
            wtimeout: float=WAIT_TIMEOUT
            ) -> Line:

        response_obj: IMatchResponse
        if isinstance(response, set):
            response_obj = ResponseOr(*response)
        else:
            response_obj = response

        our_wait_for = WaitFor(response_obj)
        self._wait_fors.append(our_wait_for)

        cur_task = asyncio.current_task()
        if cur_task is not None and cur_task in self._wait_for_fut:
            wait_for_fut = self._wait_for_fut[cur_task]
            wait_for_fut.set_result(True)

        if sent_aw is not None:
            sent_line = await sent_aw
            label = str(sent_line.id)
            our_wait_for.with_label(label)

        async with timeout(WAIT_TIMEOUT):
            return (await our_wait_for)

    async def _on_send_line(self, line: Line):
        if (line.command in ["PRIVMSG", "NOTICE", "TAGMSG"] and
                not self.cap_agreed(CAP_ECHO)):
            new_line = line.with_source(self.hostmask())
            emit = self.parse_tokens(new_line)
            self._read_queue.append((new_line, emit))

    async def _send_lines(self):
        while True:
            lines: List[SentLine] = []

            while (not lines or
                    (len(lines) < 5 and self._send_queue.qsize() > 0)):
                prio_line = await self._send_queue.get()
                lines.append(prio_line)

            for line in lines:
                async with self.throttle:
                    self._writer.write(
                        f"{line.line.format()}\r\n".encode("utf8"))

            await self._writer.drain()

            for line in lines:
                await self._on_send_line(line.line)
                await self.line_send(line.line)
                line.future.set_result(line)

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

    def send_nick(self, new_nick: str) -> Awaitable[bool]:
        fut = self.send(build("NICK", [new_nick]))
        async def _assure() -> bool:
            line = await self.wait_for({
                Response("NICK", [Folded(new_nick)], source=MASK_SELF),
                Responses([
                    ERR_BANNICKCHANGE,
                    ERR_NICKTOOFAST,
                    ERR_CANTCHANGENICK
                ], [ANY]),
                Responses([
                    ERR_NICKNAMEINUSE,
                    ERR_ERRONEUSNICKNAME,
                    ERR_UNAVAILRESOURCE
                ], [ANY, Folded(new_nick)])
            }, fut)
            return line.command == "NICK"
        return MaybeAwait(_assure)

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
            line = await self.wait_for(
                Response("PART", [Folded(name)], source=MASK_SELF),
                fut
            )
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
            channels: List[Channel] = []

            while folded_names:
                line = await self.wait_for({
                    Response(RPL_CHANNELMODEIS, [ANY, ANY]),
                    Responses(JOIN_ERR_FIRST,   [ANY, ANY]),
                    Response(ERR_USERONCHANNEL, [ANY, SELF, ANY]),
                    Response(ERR_LINKCHANNEL,   [ANY, ANY, ANY])
                }, fut)

                chan: Optional[str] = None
                if line.command == RPL_CHANNELMODEIS:
                    chan = line.params[1]
                elif line.command in JOIN_ERR_FIRST:
                    chan = line.params[1]
                elif line.command == ERR_USERONCHANNEL:
                    chan = line.params[2]
                elif line.command == ERR_LINKCHANNEL:
                    #XXX i dont like this
                    chan = line.params[2]
                    await self.wait_for(
                        Response(RPL_CHANNELMODEIS, [ANY, Folded(chan)])
                    )
                    channels.append(self.channels[self.casefold(chan)])
                    continue

                if chan is not None:
                    folded = self.casefold(chan)
                    if folded in folded_names:
                        folded_names.remove(folded)
                        channels.append(self.channels[folded])

            return channels
        return MaybeAwait(_assure)

    def send_message(self, target: str, message: str
            ) -> Awaitable[Optional[str]]:
        fut = self.send(build("PRIVMSG", [target, message]))
        async def _assure():
            line = await self.wait_for(
                Response("PRIVMSG", [Folded(target), ANY], source=MASK_SELF),
                fut
            )
            if line.command == "PRIVMSG":
                return line.params[1]
            else:
                return None
        return MaybeAwait(_assure)

    def send_whois(self,
            target: str,
            remote: bool=False
            ) -> Awaitable[Optional[Whois]]:
        args = [target]
        if remote:
            args.append(target)

        fut = self.send(build("WHOIS", args))
        async def _assure() -> Optional[Whois]:
            folded = self.casefold(target)
            params = [ANY, Folded(folded)]

            obj = Whois()
            while True:
                line = await self.wait_for(Responses([
                    ERR_NOSUCHNICK,
                    ERR_NOSUCHSERVER,
                    RPL_WHOISUSER,
                    RPL_WHOISSERVER,
                    RPL_WHOISOPERATOR,
                    RPL_WHOISIDLE,
                    RPL_WHOISCHANNELS,
                    RPL_WHOISHOST,
                    RPL_WHOISACCOUNT,
                    RPL_WHOISSECURE,
                    RPL_ENDOFWHOIS
                ], params), fut)
                if   line.command in [ERR_NOSUCHNICK, ERR_NOSUCHSERVER]:
                    return None
                elif line.command == RPL_WHOISUSER:
                    nick, user, host, _, real = line.params[1:]
                    obj.nickname = nick
                    obj.username = user
                    obj.hostname = host
                    obj.realname = real
                elif line.command == RPL_WHOISIDLE:
                    idle, signon, _ = line.params[2:]
                    obj.idle   = int(idle)
                    obj.signon = int(signon)
                elif line.command == RPL_WHOISACCOUNT:
                    obj.account = line.params[2]
                elif line.command == RPL_WHOISCHANNELS:
                    channels = list(filter(bool, line.params[2].split(" ")))
                    if obj.channels is None:
                        obj.channels = []

                    for i, channel in enumerate(channels):
                        symbols = ""
                        while channel[0] in self.isupport.prefix.prefixes:
                            symbols += channel[0]
                            channel =  channel[1:]

                        channel_user = ChannelUser(
                            Name(obj.nickname, folded),
                            Name(channel, self.casefold(channel))
                        )
                        for symbol in symbols:
                            mode = self.isupport.prefix.from_prefix(symbol)
                            if mode is not None:
                                channel_user.modes.append(mode)

                        obj.channels.append(channel_user)
                elif line.command == RPL_ENDOFWHOIS:
                    return obj
        return MaybeAwait(_assure)
