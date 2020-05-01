from asyncio   import Future
from irctokens import Line
from typing    import Any, Awaitable, Callable, Generator, Generic, TypeVar
from .matching import IMatchResponse
from .interface import IServer

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
            response: IMatchResponse):
        self._wait_fut = wait_fut
        self.response  = response
        self.deferred  = False
        self._our_fut: "Future[Line]" = Future()

    def __await__(self) -> Generator[Any, None, Line]:
        self._wait_fut.set_result(self)
        return self._our_fut.__await__()
    async def defer(self):
        self.deferred = True
        return await self

    def match(self, server: IServer, line: Line):
        return self.response.match(server, line)

    def resolve(self, line: Line):
        self._our_fut.set_result(line)
