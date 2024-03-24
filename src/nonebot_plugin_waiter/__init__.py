from __future__ import annotations

import asyncio
from typing_extensions import Self
from typing import Any, Generic, TypeVar, Callable, Iterable, Awaitable, overload

from nonebot.plugin.on import on
from nonebot.matcher import Matcher
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.dependencies import Dependent
from nonebot.internal.adapter import Bot, Event
from nonebot.internal.matcher import current_matcher
from nonebot.typing import T_State, _DependentCallable

from .config import Config

__version__ = "0.3.0"

__plugin_meta__ = PluginMetadata(
    name="Waiter 插件",
    description="提供一个 got-and-reject 会话控制的替代方案，可自由控制超时时间",
    usage="unimsg: UniMsg",
    homepage="https://github.com/RF-Tar-Railt/nonebot-plugin-waiter",
    type="library",
    config=Config,
    supported_adapters=None,
    extra={
        "author": "RF-Tar-Railt",
        "priority": 1,
        "version": __version__,
    },
)

plugin_config = get_plugin_config(Config)

R = TypeVar("R")
R1 = TypeVar("R1")
T = TypeVar("T")
T1 = TypeVar("T1")


class WaiterIterator(Generic[R, T]):
    def __init__(self, waiter: Waiter[R], default: T, timeout: float = plugin_config.waiter_timeout):
        self.waiter = waiter
        self.timeout = timeout
        self.default = default

    def __aiter__(self) -> Self:
        return self

    @overload
    def __anext__(self: WaiterIterator[R1, None]) -> Awaitable[R1 | None]:
        ...

    @overload
    def __anext__(self: WaiterIterator[R1, T1]) -> Awaitable[R1 | T1]:
        ...

    def __anext__(self):  # type: ignore
        return self.waiter.wait(default=self.default, timeout=self.timeout)  # type: ignore


class Waiter(Generic[R]):
    future: asyncio.Future
    handler: _DependentCallable[R]

    def __init__(
        self,
        waits: list[type[Event] | str],
        handler: _DependentCallable[R],
        matcher: type[Matcher] | Matcher,
        parameterless: Iterable[Any] | None = None,
    ):
        if waits:
            event_types = tuple([e for e in waits if not isinstance(e, str)])
            event_str_types = tuple([e for e in waits if isinstance(e, str)])
        else:
            event_types = ()
            event_str_types = (matcher.type,)
        self.future = asyncio.Future()
        _handler = Dependent[Any].parse(
            call=handler, parameterless=parameterless, allow_types=matcher.HANDLER_PARAM_TYPES
        )

        async def wrapper(matcher: Matcher, bot: Bot, event: Event, state: T_State):
            if event_types and not isinstance(event, event_types):
                matcher.skip()
            if event_str_types and event.get_type() not in event_str_types:
                matcher.skip()
            if self.future.done():
                matcher.skip()
            result = await _handler(
                matcher=self,
                bot=bot,
                event=event,
                state=state,
            )
            if result is not None and not self.future.done():
                self.future.set_result(result)
                matcher.stop_propagation()
                await matcher.finish()
            matcher.skip()

        self.handler = wrapper

    def __aiter__(self) -> WaiterIterator[R, None]:
        return WaiterIterator(self, None)

    @overload
    def __call__(self, *, default: T, timeout: float = 120) -> WaiterIterator[R, T]:
        ...

    @overload
    def __call__(self, *, timeout: float = 120) -> WaiterIterator[R, None]:
        ...

    def __call__(
        self, *, default: T | None = None, timeout: float = plugin_config.waiter_timeout
    ) -> WaiterIterator[R, T] | WaiterIterator[R, None]:
        """等待用户输入并返回结果

        参数:
            default: 超时时返回的默认值
            timeout: 等待超时时间
        """
        return WaiterIterator(self, default, timeout)  # type: ignore

    @overload
    async def wait(self, *, default: R | T, timeout: float = plugin_config.waiter_timeout) -> R | T:
        ...

    @overload
    async def wait(self, *, timeout: float = plugin_config.waiter_timeout) -> R | None:
        ...

    async def wait(
        self, *, default: R | T | None = None, timeout: float = plugin_config.waiter_timeout
    ) -> R | T | None:
        """等待用户输入并返回结果

        参数:
            default: 超时时返回的默认值
            timeout: 等待超时时间
        """
        matcher = on(priority=0, block=False, handlers=[self.handler])
        try:
            return await asyncio.wait_for(self.future, timeout)
        except asyncio.TimeoutError:
            return default
        finally:
            self.future = asyncio.Future()
            try:
                matcher.destroy()
            except (IndexError, ValueError):
                pass


def waiter(
    waits: list[type[Event] | str],
    matcher: type[Matcher] | Matcher | None = None,
    parameterless: Iterable[Any] | None = None,
) -> Callable[[_DependentCallable[R]], Waiter[R]]:
    """装饰一个函数来创建一个 `Waiter` 对象用以等待用户输入

    函数内需要自行判断输入是否符合预期并返回结果

    参数:
        waits: 等待的事件类型列表，可以是 `Event` 的类型或事件的 `get_type()` 返回值；
                如果为空则继承 `matcher` 参数的事件响应器类型
        matcher: 所属的 `Matcher` 对象，如果不指定则使用当前上下文的 `Matcher`
        parameterless: 非参数类型依赖列表
    """
    if not matcher:
        try:
            matcher = current_matcher.get()
        except LookupError:
            raise RuntimeError("No matcher found.")

    def wrapper(func: _DependentCallable[R]):
        return Waiter(waits, func, matcher, parameterless)

    return wrapper
