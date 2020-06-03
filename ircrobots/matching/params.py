from re           import compile as re_compile
from typing       import Optional, Pattern, Union
from irctokens    import Hostmask
from ..interface  import (IMatchResponseParam, IMatchResponseValueParam,
    IMatchResponseHostmask, IServer)
from ..glob       import Glob, compile as glob_compile
from .. import formatting

class Any(IMatchResponseParam):
    def __repr__(self) -> str:
        return "Any()"
    def match(self, server: IServer, arg: str) -> bool:
        return True
ANY = Any()

# NOT
# FORMAT FOLD
# REGEX
# LITERAL

class Literal(IMatchResponseValueParam):
    def __init__(self, value: str):
        self._value = value
    def __repr__(self) -> str:
        return f"{self._value!r}"

    def value(self, server: IServer) -> str:
        return self._value
    def set_value(self, value: str):
        self._value = value
    def match(self, server: IServer, arg: str) -> bool:
        return arg == self._value

TYPE_MAYBELIT =       Union[str, IMatchResponseParam]
TYPE_MAYBELIT_VALUE = Union[str, IMatchResponseValueParam]
def _assure_lit(value: TYPE_MAYBELIT_VALUE) -> IMatchResponseValueParam:
    if isinstance(value, str):
        return Literal(value)
    else:
        return value

class Not(IMatchResponseParam):
    def __init__(self, param: IMatchResponseParam):
        self._param = param
    def __repr__(self) -> str:
        return f"Not({self._param!r})"
    def match(self, server: IServer, arg: str) -> bool:
        return not self._param.match(server, arg)

class ParamValuePassthrough(IMatchResponseValueParam):
    _value: IMatchResponseValueParam
    def value(self, server: IServer):
        return self._value.value(server)
    def set_value(self, value: str):
        self._value.set_value(value)

class Folded(ParamValuePassthrough):
    def __init__(self, value: TYPE_MAYBELIT_VALUE):
        self._value = _assure_lit(value)
        self._folded = False
    def __repr__(self) -> str:
        return f"Folded({self._value!r})"
    def match(self, server: IServer, arg: str) -> bool:
        if not self._folded:
            value  = self.value(server)
            folded = server.casefold(value)
            self.set_value(folded)
            self._folded = True

        return self._value.match(server, server.casefold(arg))

class Formatless(IMatchResponseParam):
    def __init__(self, value: TYPE_MAYBELIT_VALUE):
        self._value = _assure_lit(value)
    def __repr__(self) -> str:
        brepr = super().__repr__()
        return f"Formatless({brepr})"
    def match(self, server: IServer, arg: str) -> bool:
        strip = formatting.strip(arg)
        return self._value.match(server, strip)

class Regex(IMatchResponseParam):
    def __init__(self, value: str):
        self._value = value
        self._pattern: Optional[Pattern] = None
    def match(self, server: IServer, arg: str) -> bool:
        if self._pattern is None:
            self._pattern = re_compile(self._value)
        return bool(self._pattern.search(arg))

class Self(IMatchResponseParam):
    def __repr__(self) -> str:
        return "Self()"
    def match(self, server: IServer, arg: str) -> bool:
        return server.casefold(arg) == server.nickname_lower
SELF = Self()

class MaskSelf(IMatchResponseHostmask):
    def __repr__(self) -> str:
        return "MaskSelf()"
    def match(self, server: IServer, hostmask: Hostmask):
        return server.casefold(hostmask.nickname) == server.nickname_lower
MASK_SELF = MaskSelf()

class Nick(IMatchResponseHostmask):
    def __init__(self, nickname: str):
        self._nickname = nickname
        self._folded: Optional[str] = None
    def __repr__(self) -> str:
        return f"Nick({self._nickname!r})"
    def match(self, server: IServer, hostmask: Hostmask):
        if self._folded is None:
            self._folded = server.casefold(self._nickname)
        return self._folded == server.casefold(hostmask.nickname)

class Mask(IMatchResponseHostmask):
    def __init__(self, mask: str):
        self._mask = mask
        self._compiled: Optional[Glob]
    def __repr__(self) -> str:
        return f"Mask({self._mask!r})"
    def match(self, server: IServer, hostmask: Hostmask):
        if self._compiled is None:
            self._compiled = glob_compile(self._mask)
        return self._compiled.match(str(hostmask))
