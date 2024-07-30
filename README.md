# nonebot-plugin-waiter

该插件提供一个 got-and-reject 会话控制的替代方案，可自由控制超时时间

## 安装

```shell
pip install nonebot-plugin-waiter
```

## 使用

### 导入

```python
from nonebot_plugin_waiter import waiter
```

### 创建

```python
...
@waiter()
async def check(event: Event):
    ...
```

`waiter` 装饰一个函数来创建一个 `Waiter` 对象用以等待预期事件

**该函数可以使用依赖注入**

函数内需要自行判断输入事件是否符合预期并返回相应结果以供外层 handler 继续处理

`waiter` 有如下参数：

- waits: 等待的事件类型列表，可以是 `Event` 的类型或事件的 `get_type()` 返回值；
    如果 waits 为空则继承 `matcher` 参数的事件响应器类型
- matcher: 所属的 `Matcher` 对象，如果不指定则使用当前上下文的 `Matcher`
- parameterless: 非参数类型依赖列表
- keep_session: 是否保持会话，即仅允许会话发起者响应
- rule: 事件响应规则，例如 `to_me()`
- block: waiter 成功响应后是否阻塞事件传递，默认为 `True`

### 等待

可直接用 `Waiter.wait` 等待函数返回结果：

```python
resp = await check.wait(timeout=60, default=False)
```

参数：

- before: 等待前发送的消息
- default: 超时时返回的默认值
- timeout: 等待超时时间

或使用异步迭代器持续等待，直到满足结果才退出循环。适合多轮对话：

```python
async for resp in check(timeout=60, default=False):
    ...
```

参数：

- default: 超时时返回的默认值
- timeout: 等待超时时间
- retry: 重试次数，不设置则无限重试
- prompt: 重试时发送的消息，若没有设置 `retry` 则不发送

### 便捷函数

插件提供了一个 `prompt` 函数用于直接等待用户输入，适用于等待用户输入文本消息：

```python
from nonebot_plugin_waiter import prompt

resp = await prompt("请输入XXX", timeout=60)
```

相应的，同时提供了一个 `prompt_until` 函数用于可重试一定次数地等待用户输入。

```python
from nonebot_plugin_waiter import prompt_until

resp = await prompt_until(
    "请输入数字",
    lambda msg: msg.extract_plain_text().isdigit(),
    timeout=60,
    retry=5,
    retry_prompt="输入错误，请输入数字。剩余次数：{count}",
)
```

基于此，还有一个 `suggest` 函数，用于向用户展示候选项并等待输入。

```python
from nonebot_plugin_waiter import suggest

resp = await suggest("请选择xxx", ["a", "b", "c", "d"])
```

`suggest_not_in` 函数用于等待候选项以外的用户输入

```python
resp = await suggest_not_in("XX已存在，请输入新的XX", not_expect=["a", "b", "c", "d"])
```

## 示例

等待用户输入数字，超时时间为 60 秒，此时 waits 接收所有来自当前用户的消息事件。

```python
from nonebot import on_command
from nonebot.adapters import Event
from nonebot_plugin_waiter import waiter, prompt

test = on_command("test")

@test.handle()
async def _():
    await test.send("请输入数字")

    @waiter(waits=["message"], keep_session=True)
    async def check(event: Event):
        return event.get_plaintext()

    resp = await check.wait(timeout=60)
    # 上面的代码等价于下面的代码
    # resp = await prompt("请输入数字", timeout=60)
    if resp is None:
        await test.send("等待超时")
        return
    if not resp.isdigit():
        await test.send("无效输入")
        return
    await test.finish(f"你输入了{resp}")
```

等待用户输入数字，超时时间为 30 秒，只允许重试 5 次，此时 waits 接收所有来自当前用户的消息事件。

```python
from nonebot import on_command
from nonebot.adapters import Event
from nonebot_plugin_waiter import waiter

test = on_command("test")

@test.handle()
async def _():
    await test.send("请输入数字")

    @waiter(waits=["message"], keep_session=True)
    async def check(event: Event):
        return event.get_plaintext()

    async for resp in check(timeout=30, retry=5, prompt="输入错误，请输入数字。剩余次数：{count}"):
        if resp is None:
            await test.send("等待超时")
            break
        if not resp.isdigit():
            continue
        await test.send(f"你输入了{resp}")
        break
    else:
        await test.send("输入失败")
```

在 telegram 适配器下等待用户点击按钮，超时时间为 30 秒，此时 waits 接收 telegram 的 CallbackQueryEvent 事件。

```python
from nonebot import on, on_command
from nonebot.adapters.telegram import Bot
from nonebot.adapters.telegram.event import (
    MessageEvent,
    CallbackQueryEvent,
)
from nonebot.adapters.telegram.model import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputTextMessageContent,
    InlineQueryResultArticle,
)

inline = on_command("inline")

@inline.handle()
async def _(bot: Bot, event: MessageEvent):
    await bot.send(
        event,
        "Hello InlineKeyboard !",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [
                    InlineKeyboardButton(
                        text="Say hello to me",
                        callback_data="hello",
                    )
                ],
            ]
        ),
    )

    @waiter(waits=[CallbackQueryEvent])
    async def check(event1: CallbackQueryEvent):
        if ...:
            return event1.id, event1.message

    resp = await check.wait(timeout=30)
    if resp is None:
        await inline.finish("等待超时")
    _id, _message = resp
    if _message:
        await bot.edit_message_text(
            "Hello CallbackQuery!", _message.chat.id, _message.message_id
        )
        await bot.answer_callback_query(_id, text="Hello CallbackQuery!")
    await inline.finish()
```

配合 [`nonebot-plugin-session`](https://github.com/noneplugin/nonebot-plugin-session) 插件使用，实现在群内的多轮会话游戏：

```python
from nonebot import on_command
from nonebot.adapters import Event
from nonebot_plugin_waiter import waiter
from nonebot_plugin_session import EventSession, SessionIdType

game = on_command("game")

@game.handle()
async def main(event: Event, session: EventSession):
    session_id = session.get_id(SessionIdType.GROUP)
    gm = Game(event.get_user_id(), session_id)
    if gm.already_start():
        await game.finish("游戏已经开始了, 请不要重复开始")
    gm.start()
    await game.send(f"开始游戏\n输入 “取消” 结束游戏")

    @waiter(waits=["message"], block=False)
    async def listen(_event: Event, _session: EventSession):
        if _session.get_id(SessionIdType.GROUP) != session_id:
            return
        text = _event.get_message().extract_plain_text()
        if text == "取消":
            return False
        return await gm.handle(text)

    async for resp in listen(timeout=60):
        if resp is False:
            await game.finish("游戏已取消")
            gm.finish()
            break
        if resp is None:
            await game.finish("游戏已超时, 请重新开始")
            gm.finish()
            break
        await game.send(resp)
        if gm.is_finish():
            await game.finish("游戏结束")
            break
```