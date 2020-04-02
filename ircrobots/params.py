from typing      import Optional
from dataclasses import dataclass

class SASLParams(object):
    def __init__(self,
            mechanism: str,
            username:  str="",
            password:  str=""):
        self.mechanism = mechanism.upper()
        self.username  = username
        self.password  = password

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
