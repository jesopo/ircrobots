from typing      import List, Optional
from dataclasses import dataclass, field

class SASLParams(object):
    mechanism: str

@dataclass
class _SASLUserPass(SASLParams):
    username:  str
    password:  str

class SASLUserPass(_SASLUserPass):
    mechanism = "USERPASS"
class SASLSCRAM(_SASLUserPass):
    mechanism = "SCRAM"
class SASLExternal(SASLParams):
    mechanism = "EXTERNAL"

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

    reconnect:     int = 10 # seconds
    alt_nicknames: List[str] = field(default_factory=list)

    autojoin:  List[str] = field(default_factory=list)

    @staticmethod
    def from_hoststring(
            nickname:   str,
            hoststring: str
            ) -> "ConnectionParams":

        host, _, port_s = hoststring.strip().partition(":")

        if port_s.startswith("+"):
            tls    = True
            port_s = port_s.lstrip("+") or "6697"
        elif not port_s:
            tls    = False
            port_s = "6667"
        else:
            tls    = False

        return ConnectionParams(nickname, host, int(port_s), tls)
