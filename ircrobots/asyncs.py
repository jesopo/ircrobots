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
            deadline: float):
        self.response = response
        self.deadline = deadline
        self._label:   Optional[str] = None
        self._our_fut: "Future[Line]" = Future()

    def __await__(self) -> Generator[Any, None, Line]:
        return self._our_fut.__await__()

    def with_label(self, label: str):
        self._label = label

    def match(self, server: IServer, line: Line):
        if (self._label is not None and
                line.tags is not None):
            label = TAG_LABEL.get(line.tags)
            if (label is not None and
                    label == self._label):
                return True
        return self.response.match(server, line)

    def resolve(self, line: Line):
        self._our_fut.set_result(line)
