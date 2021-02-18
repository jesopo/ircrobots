from asyncio    import Future
from typing     import (Any, Awaitable, Callable, Generator, Generic, Optional,
    TypeVar)

from irctokens  import Line
from .matching  import IMatchResponse
from .interface import IServer
from .ircv3     import TAG_LABEL

TEvent = TypeVar("TEvent")
class MaybeAwait(Generic[TEvent]):
    def __init__(self, func: Callable[[], Awaitable[TEvent]]):
        self._func = func

    def __await__(self) -> Generator[Any, None, TEvent]:
        coro = self._func()
        return coro.__await__()

class WaitFor(object):
    def __init__(self,
            response: IMatchResponse,
            label:    Optional[str]=None):
        self.response = response
        self._label   = label

    def match(self, server: IServer, line: Line):
        if (self._label is not None and
                line.tags is not None):
            label = TAG_LABEL.get(line.tags)
            if (label is not None and
                    label == self._label):
                return True
        return self.response.match(server, line)
