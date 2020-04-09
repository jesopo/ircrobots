from typing     import List, Optional
from irctokens  import Line
from ircstates  import NUMERIC_NAMES
from .interface import IServer, IMatchResponse, IMatchResponseParam

class Responses(IMatchResponse):
    def __init__(self,
            commands: List[str],
            params:   List[IMatchResponseParam]=[]):
        self._commands = commands
        self._params   = params
    def __repr__(self) -> str:
        return f"Responses({self._commands!r}: {self._params!r})"

    def match(self, server: IServer, line: Line) -> bool:
        for command in self._commands:
            if line.command == command:
                for i, param in enumerate(self._params):
                    if (i >= len(line.params) or
                            not param.match(server, line.params[i])):
                        continue
                else:
                    return True
        else:
            return False

class Response(Responses):
    def __init__(self,
            command: str,
            params:  List[IMatchResponseParam]=[]):
        super().__init__([command], params)

    def __repr__(self) -> str:
        return f"Response({self._commands[0]}: {self._params!r})"


class Numeric(Response):
    def __init__(self,
            name:    str,
            params:  List[IMatchResponseParam]=[]):
        super().__init__(NUMERIC_NAMES.get(name, name), params)

class Numerics(Responses):
    def __init__(self,
            numerics: List[str],
            params:   List[IMatchResponseParam]=[]):
        self._numerics = numerics
        numerics = [NUMERIC_NAMES.get(n, n) for n in numerics]
        super().__init__(numerics, params)

    def __repr__(self) -> str:
        return f"Numerics({self._numerics!r}: {self._params!r})"

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

class ParamFolded(IMatchResponseParam):
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
