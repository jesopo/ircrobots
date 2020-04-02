from typing import Optional
from enum import IntEnum
from dataclasses import dataclass

from ircstates import Server
from irctokens import Line

from .ircv3 import Capability
from .sasl  import SASLParams

@dataclass
class ConnectionParams(object):
    nickname: str
    host:     str
    port:     int
    ssl:      bool

    username: Optional[str] = None
    realname: Optional[str] = None
    bindhost: Optional[str] = None

    sasl: Optional[SASLParams] = None

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

class IServer(Server):
    params:  ConnectionParams

    async def send_raw(self, line: str, priority=SendPriority.DEFAULT):
        pass
    async def send(self, line: Line, priority=SendPriority.DEFAULT):
        pass

    def set_throttle(self, rate: int, time: float):
        pass

    async def connect(self, params: ConnectionParams):
        pass

    async def queue_capability(self, cap: Capability):
        pass

    async def line_written(self, line: Line):
        pass
