from typing      import Optional
from dataclasses import dataclass

@dataclass
class SASLParams(object):
    mechanism: str
    username:  Optional[str] = None
    password:  Optional[str] = None
class SASLUserPass(SASLParams):
    def __init__(self, username: str, password: str):
        super().__init__("USERPASS", username, password)
class SASLExternal(SASLParams):
    def __init__(self):
        super().__init__("EXTERNAL")

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
