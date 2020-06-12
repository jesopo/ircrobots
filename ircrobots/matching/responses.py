from typing      import List, Optional, Sequence, Union
from irctokens   import Line
from ..interface import (IServer, IMatchResponse, IMatchResponseParam,
    IMatchResponseHostmask)
from .params     import *

TYPE_PARAM = Union[str, IMatchResponseParam]
class Responses(IMatchResponse):
    def __init__(self,
            commands: Sequence[str],
            params:   Sequence[TYPE_PARAM]=[],
            source:   Optional[IMatchResponseHostmask]=None):
        self._commands = commands
        self._source   = source

        self._params: Sequence[IMatchResponseParam] = []
        for param in params:
            if isinstance(param, str):
                self._params.append(Literal(param))
            elif isinstance(param, IMatchResponseParam):
                self._params.append(param)

    def __repr__(self) -> str:
        return f"Responses({self._commands!r}: {self._params!r})"

    def match(self, server: IServer, line: Line) -> bool:
        for command in self._commands:
            if (line.command == command and (
                    self._source is None or (
                        line.hostmask is not None and
                        self._source.match(server, line.hostmask)
                    ))):

                for i, param in enumerate(self._params):
                    if (i >= len(line.params) or
                            not param.match(server, line.params[i])):
                        break
                else:
                    return True
        else:
            return False

class Response(Responses):
    def __init__(self,
            command: str,
            params:  Sequence[TYPE_PARAM]=[],
            source:  Optional[IMatchResponseHostmask]=None):
        super().__init__([command], params, source=source)

    def __repr__(self) -> str:
        return f"Response({self._commands[0]}: {self._params!r})"

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
