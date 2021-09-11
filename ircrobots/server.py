import asyncio
from asyncio     import Future, PriorityQueue
from typing      import (AsyncIterable, Awaitable, Deque, Dict, Iterable, List,
    Optional, Set, Tuple, Union)
from collections import deque
from time        import monotonic

import anyio
from asyncio_rlock      import RLock
from asyncio_throttle   import Throttler
from async_timeout      import timeout as timeout_
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

        self.throttle = Throttler(rate_limit=100, period=1)

        self.sasl_state = SASLResult.NONE
        self.last_read  = monotonic()

        self._sent_count:  int = 0
        self._send_queue: PriorityQueue[SentLine] = PriorityQueue()
        self.desired_caps: Set[ICapability] = set([])

        self._read_queue:    Deque[Line] = deque()
        self._process_queue: Deque[Tuple[Line, Optional[Emit]]] = deque()

        self._ping_sent   = False
        self._read_lguard = RLock()
        self.read_lock    = self._read_lguard
        self._read_lwork  = asyncio.Lock()
        self._wait_for    = asyncio.Event()

        self._pending_who: Deque[str] = deque()
        self._alt_nicks:   List[str] = []

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

        alt_nicks = self.params.alt_nicknames
        if not alt_nicks:
            alt_nicks = [nickname+"_"*i for i in range(1, 4)]
        self._alt_nicks =  alt_nicks

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

        elif line.command == RPL_ENDOFWHO:
            chan = self.casefold(line.params[1])
            if (self._pending_who and
                    self._pending_who[0] == chan):
                self._pending_who.popleft()
                await self._next_who()

        elif (line.command in {ERR_NICKNAMEINUSE, ERR_ERRONEUSNICKNAME} and
                not self.registered):
            if self._alt_nicks:
                nick = self._alt_nicks.pop(0)
                await self.send(build("NICK", [nick]))
            else:
                await self.send(build("QUIT"))

        elif line.command in [RPL_ENDOFMOTD, ERR_NOMOTD]:
            # we didn't get the nickname we wanted. watch for it if we can
            if not self.nickname == self.params.nickname:
                target = self.params.nickname
                if self.isupport.monitor is not None:
                    await self.send(build("MONITOR", ["+", target]))
                elif self.isupport.watch is not None:
                    await self.send(build("WATCH", [f"+{target}"]))

        # has someone just stopped using the nickname we want?
        elif line.command == RPL_LOGOFF:
            await self._check_regain([line.params[1]])
        elif line.command == RPL_MONOFFLINE:
            await self._check_regain(line.params[1].split(","))
        elif (line.command in ["NICK", "QUIT"] and
                line.source is not None):
            await self._check_regain([line.hostmask.nickname])

        elif emit is not None:
            if emit.command == RPL_WELCOME:
                await self.send(build("WHO", [self.nickname]))
                self.set_throttle(THROTTLE_RATE, THROTTLE_TIME)

                if self.params.autojoin:
                    await self._batch_joins(self.params.autojoin)

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
                    chan  = emit.channel.name_lower
                    await self.send(build("MODE", [chan]))

                    modes = "".join(self.isupport.chanmodes.a_modes)
                    await self.send(build("MODE", [chan, f"+{modes}"]))

                    self._pending_who.append(chan)
                    if len(self._pending_who) == 1:
                        await self._next_who()

        await self.line_read(line)

    async def _check_regain(self, nicks: List[str]):
        for nick in nicks:
            if (self.casefold_equals(nick, self.params.nickname) and
                    not self.nickname == self.params.nickname):
                await self.send(build("NICK", [self.params.nickname]))

    async def _batch_joins(self,
            channels: List[str],
            batch_n:  int=10):
        #TODO: do as many JOINs in one line as we can fit
        #TODO: channel keys

        for i in range(0, len(channels), batch_n):
            batch = channels[i:i+batch_n]
            await self.send(build("JOIN", [",".join(batch)]))

    async def _next_who(self):
        if self._pending_who:
            chan = self._pending_who[0]
            if self.isupport.whox:
                await self.send(self.prepare_whox(chan))
            else:
                await self.send(build("WHO", [chan]))

    async def _read_line(self, timeout: float) -> Optional[Line]:
        while True:
            if self._read_queue:
                return self._read_queue.popleft()

            try:
                async with timeout_(timeout):
                    data = await self._reader.read(1024)
            except asyncio.TimeoutError:
                return None

            self.last_read = monotonic()
            lines          = self.recv(data)
            for line in lines:
                self.line_preread(line)
                self._read_queue.append(line)

    async def _read_lines(self):
        while True:
            async with self._read_lguard:
                pass

            if not self._process_queue:
                async with self._read_lwork:
                    read_aw  = self._read_line(PING_TIMEOUT)
                    dones, notdones = await asyncio.wait(
                        [read_aw, self._wait_for.wait()],
                        return_when=asyncio.FIRST_COMPLETED
                    )
                    self._wait_for.clear()

                    for done in dones:
                        if isinstance(done.result(), Line):
                            self._ping_sent = False
                            line = done.result()
                            emit = self.parse_tokens(line)
                            self._process_queue.append((line, emit))
                        elif done.result() is None:
                            if not self._ping_sent:
                                await self.send(build("PING", ["hello"]))
                                self._ping_sent = True
                            else:
                                await self.disconnect()
                                raise ServerDisconnectedException()
                    for notdone in notdones:
                        notdone.cancel()

            else:
                line, emit = self._process_queue.popleft()
                await self._on_read(line, emit)

    async def wait_for(self,
            response: Union[IMatchResponse, Set[IMatchResponse]],
            sent_aw:  Optional[Awaitable[SentLine]]=None,
            timeout:  float=WAIT_TIMEOUT
            ) -> Line:

        response_obj: IMatchResponse
        if isinstance(response, set):
            response_obj = ResponseOr(*response)
        else:
            response_obj = response

        async with self._read_lguard:
            self._wait_for.set()
            async with self._read_lwork:
                async with timeout_(timeout):
                    while True:
                        line = await self._read_line(timeout)
                        if line:
                            self._ping_sent = False
                            emit = self.parse_tokens(line)
                            self._process_queue.append((line, emit))
                            if response_obj.match(self, line):
                                return line

    async def _on_send_line(self, line: Line):
        if (line.command in ["PRIVMSG", "NOTICE", "TAGMSG"] and
                not self.cap_agreed(CAP_ECHO)):
            new_line = line.with_source(self.hostmask())
            self._read_queue.append(new_line)

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
                                channel_user.modes.add(mode)

                        obj.channels.append(channel_user)
                elif line.command == RPL_ENDOFWHOIS:
                    return obj
        return MaybeAwait(_assure)
