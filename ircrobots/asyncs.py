from asyncio   import Future
from irctokens import Line
from typing    import Any, Awaitable, Callable, Generator, Generic, TypeVar
from .matching import IMatchResponse

TEvent = TypeVar("TEvent")
class MaybeAwait(Generic[TEvent]):
    def __init__(self, func: Callable[[], Awaitable[TEvent]]):
        self._func = func

    def __await__(self) -> Generator[Any, None, TEvent]:
        coro = self._func()
        return coro.__await__()

class WaitFor(object):
    def __init__(self, response: IMatchResponse):
        self.response = response
        self._fut: "Future[Line]" = Future()

    def __await__(self) -> Generator[Any, None, Line]:
        return self._fut.__await__()

    def resolve(self, line: Line):
        self._fut.set_result(line)
