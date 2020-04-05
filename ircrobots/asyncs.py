from typing import Any, Awaitable, Callable, Generator, Generic, TypeVar

TEvent = TypeVar("TEvent")
class MaybeAwait(Generic[TEvent]):
    def __init__(self, func: Callable[[], Awaitable[TEvent]]):
        self._func = func

    def __await__(self) -> Generator[Any, None, TEvent]:
        coro = self._func()
        return coro.__await__()
