from asyncio    import Future
from irctokens  import Line
from typing     import (Any, Awaitable, Callable, Generator, Generic, Optional,
    TypeVar)
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
            wait_fut: "Future[WaitFor]",
            response: IMatchResponse,
            label:    Optional[str]):
        self._wait_fut = wait_fut
        self.response  = response
        self._label    = label
        self.deferred  = False
        self._our_fut: "Future[Line]" = Future()

    def __await__(self) -> Generator[Any, None, Line]:
        self._wait_fut.set_result(self)
        return self._our_fut.__await__()
    async def defer(self):
        self.deferred = True
        return await self

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
