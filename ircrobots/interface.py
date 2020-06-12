from asyncio import Future
from typing  import Awaitable, Iterable, List, Optional, Set, Tuple, Union
from enum    import IntEnum

from ircstates import Server, Emit
from irctokens import Line, Hostmask

from .params   import ConnectionParams, SASLParams, STSPolicy, ResumePolicy

class ITCPReader(object):
    async def read(self, byte_count: int):
        pass
class ITCPWriter(object):
    def write(self, data: bytes):
        pass

    def get_peer(self) -> Tuple[str, int]:
        pass

    async def drain(self):
        pass
    async def close(self):
        pass

class ITCPTransport(object):
    async def connect(self,
            hostname:   str,
            port:       int,
            tls:        bool,
            tls_verify: bool=True,
            bindhost:   Optional[str]=None
            ) -> Tuple[ITCPReader, ITCPWriter]:
        pass

class SendPriority(IntEnum):
    HIGH   = 0
    MEDIUM = 10
    LOW    = 20
    DEFAULT = MEDIUM

class SentLine(object):
    def __init__(self,
            id:       int,
            priority: int,
            line:     Line):
        self.id             = id
        self.priority       = priority
        self.line           = line
        self.future: "Future[SentLine]" = Future()

    def __lt__(self, other: "SentLine") -> bool:
        return self.priority < other.priority

class ICapability(object):
    def available(self, capabilities: Iterable[str]) -> Optional[str]:
        pass

    def match(self, capability: str) -> bool:
        pass

    def copy(self) -> "ICapability":
        pass

class IMatchResponse(object):
    def match(self, server: "IServer", line: Line) -> bool:
        pass
class IMatchResponseParam(object):
    def match(self, server: "IServer", arg: str) -> bool:
        pass
class IMatchResponseValueParam(IMatchResponseParam):
    def value(self, server: "IServer"):
        pass
    def set_value(self, value: str):
        pass
class IMatchResponseHostmask(object):
    def match(self, server: "IServer", hostmask: Hostmask) -> bool:
        pass

class IServer(Server):
    bot:          "IBot"
    disconnected: bool
    params:       ConnectionParams
    desired_caps: Set[ICapability]
    last_read:    float

    def send_raw(self, line: str, priority=SendPriority.DEFAULT
            ) -> Awaitable[SentLine]:
        pass
    def send(self, line: Line, priority=SendPriority.DEFAULT
            ) -> Awaitable[SentLine]:
        pass

    def wait_for(self,
            response: Union[IMatchResponse, Set[IMatchResponse]]
            ) -> Awaitable[Line]:
        pass

    def set_throttle(self, rate: int, time: float):
        pass

    def server_address(self) -> Tuple[str, int]:
        pass

    async def connect(self,
            transport: ITCPTransport,
            params:    ConnectionParams):
        pass
    async def disconnect(self):
        pass

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

    def cap_agreed(self, capability: ICapability) -> bool:
        pass
    def cap_available(self, capability: ICapability) -> Optional[str]:
        pass

    async def sasl_auth(self, sasl: SASLParams) -> bool:
        pass

class IBot(object):
    def create_server(self, name: str) -> IServer:
        pass
    async def disconnected(self, server: IServer):
        pass

    async def disconnect(self, server: IServer):
        pass

    async def add_server(self, name: str, params: ConnectionParams) -> IServer:
        pass

    async def run(self):
        pass
