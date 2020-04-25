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
class SASLSCRAM(SASLParams):
    def __init__(self, username: str, password: str):
        super().__init__("SCRAM", username, password)
class SASLExternal(SASLParams):
    def __init__(self):
        super().__init__("EXTERNAL")

@dataclass
class STSPolicy(object):
    created:  int
    port:     int
    duration: int
    preload:  bool

@dataclass
class ResumePolicy(object):
    address: str
    token:   str

@dataclass
class ConnectionParams(object):
    nickname: str
    host:     str
    port:     int
    tls:      bool

    username: Optional[str] = None
    realname: Optional[str] = None
    bindhost: Optional[str] = None

    password:   Optional[str] = None
    tls_verify: bool = True
    sasl:       Optional[SASLParams] = None

    sts:    Optional[STSPolicy]    = None
    resume: Optional[ResumePolicy] = None
