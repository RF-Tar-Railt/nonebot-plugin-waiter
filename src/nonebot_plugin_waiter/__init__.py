from __future__ import annotations

import asyncio
from typing_extensions import Self
from collections.abc import Iterable, Awaitable
from typing import Any, Generic, TypeVar, Callable, cast, overload

from nonebot.plugin.on import on
from nonebot.matcher import Matcher
from nonebot import get_plugin_config
from nonebot.plugin import PluginMetadata
from nonebot.dependencies import Dependent
from nonebot.typing import T_State, _DependentCallable
from nonebot.internal.permission import User, Permission
from nonebot.utils import run_sync, is_coroutine_callable
from nonebot.internal.matcher import current_event, current_matcher
from nonebot.internal.adapter import Bot, Event, Message, MessageSegment, MessageTemplate

from .config import Config

__version__ = "0.6.0"

__plugin_meta__ = PluginMetadata(
    name="Waiter 插件",
    description="提供一个 got-and-reject 会话控制的替代方案，可自由控制超时时间",
    usage="@waiter(waits: list[type[Event] | str], matcher: type[Matcher] | Matcher, parameterless: Iterable[Any] | None, keep_session: bool = False)",  # noqa: E501
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
    def __init__(
        self,
        waiter: Waiter[R],
        default: T,
        timeout: float = plugin_config.waiter_timeout,
        retry: int | None = None,
        msg: Message | MessageTemplate = MessageTemplate(plugin_config.waiter_retry_prompt),
    ):
        self.waiter = waiter
        self.timeout = timeout
        self.default = default
        self.retry = retry
        self.msg = msg
        self._next_count = 0

    def __aiter__(self) -> Self:
        return self

    @overload
    def __anext__(self: WaiterIterator[R1, None]) -> Awaitable[R1 | None]: ...

    @overload
    def __anext__(self: WaiterIterator[R1, T1]) -> Awaitable[R1 | T1]: ...

    def __anext__(self):  # type: ignore
        if self.retry is None:
            return self.waiter.wait(default=self.default, timeout=self.timeout)
        msg = None
        if self._next_count > 0:
            self.retry -= 1
            if self.retry < 0:
                raise StopAsyncIteration
            if isinstance(self.msg, MessageTemplate):
                msg = self.msg.format(count=f"{self.retry + 1}")
            else:
                msg = self.msg
        try:
            return self.waiter.wait(msg, default=self.default, timeout=self.timeout)
        finally:
            self._next_count += 1


class Waiter(Generic[R]):
    future: asyncio.Future
    handler: _DependentCallable[R]

    def __init__(
        self,
        waits: list[type[Event] | str],
        handler: _DependentCallable[R],
        matcher: type[Matcher] | Matcher,
        parameterless: Iterable[Any] | None = None,
        permission: Permission | None = None,
    ):
        if waits:
            event_types = tuple([e for e in waits if not isinstance(e, str)])
            event_str_types = tuple([e for e in waits if isinstance(e, str)])
            self.event_type = event_str_types[0] if len(event_str_types) == 1 else ""
        else:
            event_types = ()
            event_str_types = (matcher.type,)
            self.event_type = matcher.type
        self.future = asyncio.Future()
        _handler = Dependent[Any].parse(
            call=handler, parameterless=parameterless, allow_types=matcher.HANDLER_PARAM_TYPES
        )

        async def wrapper(
            matcher: Matcher,
            bot: Bot,
            event: Event,
            state: T_State,
        ):
            if event_types and not isinstance(event, event_types):
                matcher.skip()
            if event_str_types and event.get_type() not in event_str_types:
                matcher.skip()
            if self.future.done():
                matcher.skip()
            result = await _handler(
                matcher=matcher,
                bot=bot,
                event=event,
                state=state,
            )
            if result is not None and not self.future.done():
                self.future.set_result(result)
                matcher.stop_propagation()
                await matcher.finish()
            matcher.skip()

        wrapper.__annotations__ = {"matcher": Matcher, "bot": Bot, "event": Event, "state": T_State}
        self.handler = wrapper
        self.permission = permission

    def __aiter__(self) -> WaiterIterator[R, None]:
        return WaiterIterator(self, None)

    @overload
    def __call__(self, *, default: T, timeout: float = 120) -> WaiterIterator[R, T]: ...

    @overload
    def __call__(self, *, timeout: float = 120) -> WaiterIterator[R, None]: ...

    @overload
    def __call__(
        self,
        *,
        retry: int,
        timeout: float = 120,
        prompt: str | Message | MessageSegment | MessageTemplate = "",
    ) -> WaiterIterator[R, None]: ...

    @overload
    def __call__(
        self,
        *,
        retry: int,
        default: T,
        timeout: float = 120,
        prompt: str | Message | MessageSegment | MessageTemplate = "",
    ) -> WaiterIterator[R, T]: ...

    def __call__(
        self,
        *,
        default: T | None = None,
        timeout: float = plugin_config.waiter_timeout,
        retry: int | None = None,
        prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_retry_prompt,
    ) -> WaiterIterator[R, T] | WaiterIterator[R, None]:
        """循环等待用户输入并返回结果，可以设置重试次数来限制循环次数

        参数:
            default: 超时时返回的默认值
            timeout: 等待超时时间
            retry:   重试次数
            prompt:  重试的提示消息
        """
        if isinstance(prompt, str):
            msg = MessageTemplate(prompt)
        elif isinstance(prompt, MessageSegment):
            msg = prompt.get_message_class()(prompt)
        else:
            msg = prompt
        return WaiterIterator(self, default, timeout, retry, msg)  # type: ignore

    @overload
    async def wait(
        self,
        before: str | Message | MessageSegment | MessageTemplate | None = None,
        *,
        default: R | T,
        timeout: float = plugin_config.waiter_timeout,
    ) -> R | T: ...

    @overload
    async def wait(
        self,
        before: str | Message | MessageSegment | MessageTemplate | None = None,
        *,
        timeout: float = plugin_config.waiter_timeout,
    ) -> R | None: ...

    async def wait(
        self,
        before: str | Message | MessageSegment | MessageTemplate | None = None,
        *,
        default: R | T | None = None,
        timeout: float = plugin_config.waiter_timeout,
    ) -> R | T | None:
        """等待用户输入并返回结果

        参数:
            before: 等待前发送的消息
            default: 超时时返回的默认值
            timeout: 等待超时时间
        """
        matcher = on(
            type=self.event_type, permission=self.permission, priority=0, block=False, handlers=[self.handler]
        )
        if before:
            await matcher.send(before)
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
    keep_session: bool = False,
) -> Callable[[_DependentCallable[R]], Waiter[R]]:
    """装饰一个函数来创建一个 `Waiter` 对象用以等待用户输入

    函数内需要自行判断输入是否符合预期并返回结果

    Args:
        waits: 等待的事件类型列表，可以是 `Event` 的类型或事件的 `get_type()` 返回值；
                如果为空则继承 `matcher` 参数的事件响应器类型
        matcher: 所属的 `Matcher` 对象，如果不指定则使用当前上下文的 `Matcher`
        parameterless: 非参数类型依赖列表
        keep_session: 是否保持会话，即仅允许会话发起者响应
    """
    if not matcher:
        try:
            matcher = current_matcher.get()
        except LookupError:
            raise RuntimeError("No matcher found.")

    if not keep_session:
        permission = None
    else:
        try:
            event = current_event.get()
        except LookupError:
            permission = None
        else:
            permission = Permission(User.from_event(event, perm=matcher.permission))

    def wrapper(func: _DependentCallable[R]):
        return Waiter(waits, func, matcher, parameterless, permission)

    return wrapper


@overload
async def prompt(
    message: str | Message | MessageSegment | MessageTemplate,
    *,
    timeout: float = plugin_config.waiter_timeout,
) -> Message | None: ...


@overload
async def prompt(
    message: str | Message | MessageSegment | MessageTemplate,
    handler: _DependentCallable[R],
    *,
    timeout: float = plugin_config.waiter_timeout,
) -> R | None: ...


async def prompt(
    message: str | Message | MessageSegment | MessageTemplate,
    handler: _DependentCallable[R] | None = None,
    timeout: float = plugin_config.waiter_timeout,
):
    """等待用户输入并返回结果

    参数:
        message: 提示消息
        timeout: 等待超时时间
    返回值:
        符合条件的用户输入
    """

    async def wrapper(event: Event):
        return event.get_message()

    wrapper.__annotations__ = {"event": Event}

    if handler is None:
        wait = waiter(["message"], keep_session=True)(wrapper)
    else:
        wait = waiter(["message"], keep_session=True)(handler)

    return await wait.wait(message, timeout=timeout)


async def call_callable(func: Callable[[str], bool], s: str) -> bool:
    if is_coroutine_callable(func):
        return await cast(Callable[[str], Awaitable[bool]], func)(s)
    else:
        return await run_sync(cast(Callable[[str], bool], func))(s)


@overload
async def prompt_until(
    message: str | Message | MessageSegment | MessageTemplate,
    checker: Callable[[Message], bool],
    *,
    matcher: type[Matcher] | Matcher | None = None,
    timeout: float = plugin_config.waiter_timeout,
    retry: int = 5,
    finish: bool = False,
    retry_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_retry_prompt,
    timeout_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_timeout_prompt,
    limited_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_limited_prompt,
) -> Message | None: ...


@overload
async def prompt_until(
    message: str | Message | MessageSegment | MessageTemplate,
    checker: Callable[[R], bool],
    handler: _DependentCallable[R],
    *,
    matcher: type[Matcher] | Matcher | None = None,
    timeout: float = plugin_config.waiter_timeout,
    retry: int = 5,
    finish: bool = False,
    retry_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_retry_prompt,
    timeout_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_timeout_prompt,
    limited_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_limited_prompt,
) -> R | None: ...


async def prompt_until(
    message: str | Message | MessageSegment | MessageTemplate,
    checker: Callable[..., bool],
    handler: _DependentCallable[R] | None = None,
    *,
    matcher: type[Matcher] | Matcher | None = None,
    timeout: float = plugin_config.waiter_timeout,
    retry: int = 5,
    finish: bool = False,
    retry_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_retry_prompt,
    timeout_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_timeout_prompt,
    limited_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_limited_prompt,
):
    """等待用户输入并返回结果

    参数:
        before: 提示消息
        matcher: 匹配器
        timeout: 等待超时时间
        retry: 重试次数
        retry_prompt: 重试时的提示信息
        timeout_prompt: 等待超时时的提示信息
        limited_prompt: 重试次数用尽时的提示信息
        rule: 验证输入的规则
        finish: 超时或重试过多时是结束
    返回值:
        符合条件的用户输入
    """
    if not matcher:
        try:
            matcher = current_matcher.get()
        except LookupError:
            raise RuntimeError("No matcher found.")

    await matcher.send(message)

    async def wrapper(event: Event):
        return event.get_message()

    wrapper.__annotations__ = {"event": Event}

    if handler is None:
        wait = waiter(waits=["message"], keep_session=True, matcher=matcher)(wrapper)
    else:
        wait = waiter(waits=["message"], keep_session=True, matcher=matcher)(handler)

    async for data in wait(timeout=timeout, retry=retry, prompt=retry_prompt):
        if data is None:
            if finish:
                await matcher.finish(timeout_prompt)
            else:
                await matcher.send(timeout_prompt)
            return
        if not checker(data):
            continue
        return data  # type: ignore
    else:
        if finish:
            await matcher.finish(limited_prompt)
        else:
            await matcher.send(limited_prompt)


async def suggest(
    message: str | Message | MessageSegment | MessageTemplate,
    expect: list[str],
    timeout: float = plugin_config.waiter_timeout,
    retry: int = 5,
    retry_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_retry_prompt,
    timeout_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_timeout_prompt,
    limited_prompt: str | Message | MessageSegment | MessageTemplate = plugin_config.waiter_limited_prompt,
):
    """等待用户输入给出的选项并返回结果

    参数:
        message: 提示消息
        expect: 候选项列表
        timeout: 等待超时时间
        retry: 重试次数
        retry_prompt: 重试时的提示信息
        timeout_prompt: 等待超时时的提示信息
        limited_prompt: 重试次数用尽时的提示信息
    返回值:
        符合条件的用户输入
    """
    try:
        matcher = current_matcher.get()
    except LookupError:
        raise RuntimeError("No matcher found.")

    if isinstance(message, MessageTemplate):
        _message = message.format(**matcher.state)
    else:
        _message = message

    _message += "\n" + plugin_config.waiter_suggest_sep.join(
        [plugin_config.waiter_suggest_hint.format(suggest=s) for s in expect]
    )

    return await prompt_until(
        _message,
        lambda msg: msg.extract_plain_text() in expect,
        matcher=matcher,
        timeout=timeout,
        retry=retry,
        retry_prompt=retry_prompt,
        timeout_prompt=timeout_prompt,
        limited_prompt=limited_prompt,
    )
