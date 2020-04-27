from re           import compile as re_compile
from typing       import Optional, Pattern
from irctokens    import Hostmask
from ..interface  import IMatchResponseParam, IMatchResponseHostmask, IServer
from ..glob       import Glob, compile as glob_compile
from .. import formatting

class Any(IMatchResponseParam):
    def __repr__(self) -> str:
        return "Any()"
    def match(self, server: IServer, arg: str) -> bool:
        return True
ANY = Any()

class Literal(IMatchResponseParam):
    def __init__(self, value: str):
        self._value = value
    def __repr__(self) -> str:
        return f"{self._value!r}"
    def match(self, server: IServer, arg: str) -> bool:
        return arg == self._value

class Not(IMatchResponseParam):
    def __init__(self, param: IMatchResponseParam):
        self._param = param
    def __repr__(self) -> str:
        return f"Not({self._param!r})"
    def match(self, server: IServer, arg: str) -> bool:
        return not self._param.match(server, arg)

class Folded(IMatchResponseParam):
    def __init__(self, value: str):
        self._value = value
        self._folded: Optional[str] = None
    def __repr__(self) -> str:
        return f"Folded({self._value!r})"
    def match(self, server: IServer, arg: str) -> bool:
        if self._folded is None:
            self._folded = server.casefold(self._value)
        return self._folded == server.casefold(arg)

class Formatless(Literal):
    def __repr__(self) -> str:
        brepr = super().__repr__()
        return f"Formatless({brepr})"
    def match(self, server: IServer, arg: str) -> bool:
        strip = formatting.strip(arg)
        return super().match(server, strip)

class Regex(IMatchResponseParam):
    def __init__(self, value: str):
        self._value = value
        self._pattern: Optional[Pattern] = None
    def match(self, server: IServer, arg: str) -> bool:
        if self._pattern is None:
            self._pattern = re_compile(self._value)
        return bool(self._pattern.search(arg))

class Nickname(IMatchResponseHostmask):
    def __init__(self, nickname: str):
        self._nickname = nickname
        self._folded: Optional[str] = None

    def __repr__(self) -> str:
        mask = f"{self._nickname}!*@*"
        return f"Hostmask({mask!r})"
    def match(self, server: IServer, hostmask: Hostmask):
        if self._folded is None:
            self._folded = server.casefold(self._nickname)
        return self._folded == server.casefold(hostmask.nickname)

class Mask(IMatchResponseHostmask):
    def __init__(self, mask: str):
        self._mask = mask
        self._compiled = Optional[Glob]
    def match(self, server: IServer, hostmask: Hostmask):
        if self._compiled is None:
            self._compiled = glob_compile(self._mask)
        return self._compiled.match(str(hostmask))
