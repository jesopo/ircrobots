from re          import compile as re_compile
from typing      import List, Optional
from dataclasses import dataclass, field

from .security import TLS, TLSNoVerify, TLSVerifyChain

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

RE_IPV6HOST = re_compile("\[([a-fA-F0-9:]+)\]")

_TLS_TYPES = {
    "+": TLSVerifyChain,
    "~": TLSNoVerify,
}
@dataclass
class ConnectionParams(object):
    nickname: str
    host:     str
    port:     int
    tls:      Optional[TLS] = field(default_factory=TLSVerifyChain)

    username: Optional[str] = None
    realname: Optional[str] = None
    bindhost: Optional[str] = None

    password:   Optional[str] = None
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

        ipv6host = RE_IPV6HOST.search(hoststring)
        if ipv6host is not None and ipv6host.start() == 0:
            host = ipv6host.group(1)
            port_s = hoststring[ipv6host.end()+1:]
        else:
            host, _, port_s = hoststring.strip().partition(":")

        tls_type: Optional[TLS] = None
        if not port_s:
            port_s = "6667"
        else:
            tls_type = _TLS_TYPES.get(port_s[0], lambda: None)()
            if tls_type is not None:
                port_s = port_s[1:] or "6697"

        return ConnectionParams(nickname, host, int(port_s), tls_type)
