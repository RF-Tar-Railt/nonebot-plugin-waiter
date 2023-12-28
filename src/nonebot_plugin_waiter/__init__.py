from __future__ import annotations

import asyncio
from typing_extensions import Self
from typing import Any, Generic, TypeVar, Iterable, Awaitable, overload

from nonebot import get_driver
from nonebot.matcher import Matcher
from nonebot.plugin.on import on_message
from nonebot.plugin import PluginMetadata
from nonebot.dependencies import Dependent
from nonebot.internal.adapter import Bot, Event
from nonebot.typing import T_State, _DependentCallable

from .config import Config

__version__ = "0.1.0"

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

global_config = get_driver().config
plugin_config = Config.parse_obj(global_config)

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
        self, handler: _DependentCallable[R], params: tuple, parameterless: Iterable[Any] | None = None
    ):
        self.future = asyncio.Future()
        _handler = Dependent[Any].parse(call=handler, parameterless=parameterless, allow_types=params)

        async def wrapper(matcher: Matcher, bot: Bot, event: Event, state: T_State):
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
        matcher = on_message(priority=0, block=False, handlers=[self.handler])
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


def waiter(matcher: type[Matcher] | Matcher, parameterless: Iterable[Any] | None = None):
    """装饰一个函数来创建一个 `Waiter` 对象用以等待用户输入

    函数内需要自行判断输入是否符合预期并返回结果

    参数:
        parameterless: 非参数类型依赖列表
    """

    def wrapper(func: _DependentCallable[R]):
        return Waiter(func, matcher.HANDLER_PARAM_TYPES, parameterless)

    return wrapper
