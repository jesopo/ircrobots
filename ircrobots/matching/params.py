from typing       import Optional
from irctokens    import Hostmask
from ..interface  import IMatchResponseParam, IMatchResponseHostmask, IServer
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

class Not(IMatchResponseParam):
    def __init__(self, param: IMatchResponseParam):
        self._param = param
    def __repr__(self) -> str:
        return f"Not({self._param!r})"
    def match(self, server: IServer, arg: str) -> bool:
        return not self._param.match(server, arg)

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
