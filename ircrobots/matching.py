from typing     import List, Optional
from irctokens  import Line
from .numerics  import NUMERIC_NAMES
from .interface import IServer, IMatchResponse, IMatchResponseParam

class Response(IMatchResponse):
    def __init__(self,
            command: str,
            params:  List[IMatchResponseParam]):
        self._command = command
        self._params  = params
    def __repr__(self) -> str:
        return f"Response({self._command}: {self._params!r})"

    def match(self, server: IServer, line: Line) -> bool:
        if line.command == self._command:
            for i, param in enumerate(self._params):
                if (i >= len(line.params) or
                        not param.match(server, line.params[i])):
                    return False
            else:
                return True
        else:
            return False

class Numeric(Response):
    def __init__(self,
            name:    str,
            params:  List[IMatchResponseParam]=[]):
        super().__init__(NUMERIC_NAMES.get(name, name), params)

class Numerics(IMatchResponse):
    def __init__(self,
            numerics: List[str]):
        self._numerics = [NUMERIC_NAMES.get(n, n) for n in numerics]
    def __repr__(self) -> str:
        return f"Numerics({self._numerics!r})"

    def match(self, server: IServer, line: Line):
        return line.command in self._numerics

class ResponseOr(IMatchResponse):
    def __init__(self, *responses: IMatchResponse):
        self._responses = responses
    def __repr__(self) -> str:
        return f"ResponseOr({self._responses!r})"
    def match(self, server: IServer, line: Line) -> bool:
        for response in self._responses:
            if response.match(server, line):
                return True
        else:
            return False

class ParamAny(IMatchResponseParam):
    def __repr__(self) -> str:
        return "Any()"
    def match(self, server: IServer, arg: str) -> bool:
        return True

class ParamLiteral(IMatchResponseParam):
    def __init__(self, value: str):
        self._value = value
    def __repr__(self) -> str:
        return f"Literal({self._value!r})"
    def match(self, server: IServer, arg: str) -> bool:
        return self._value == arg

class FoldString(IMatchResponseParam):
    def __init__(self, value: str):
        self._value = value
        self._folded: Optional[str] = None
    def __repr__(self) -> str:
        return f"FoldString({self._value!r})"
    def match(self, server: IServer, arg: str) -> bool:
        if self._folded is None:
            self._folded = server.casefold(self._value)
        return self._folded == server.casefold(arg)

class ParamNot(IMatchResponseParam):
    def __init__(self, param: IMatchResponseParam):
        self._param = param
    def __repr__(self) -> str:
        return f"Not({self._param!r})"
    def match(self, server: IServer, arg: str) -> bool:
        return not self._param.match(server, arg)
