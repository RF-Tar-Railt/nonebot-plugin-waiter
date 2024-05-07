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

函数内需要自行判断输入事件是否符合预期并返回结果

`waiter` 有如下参数：

- waits: 等待的事件类型列表，可以是 `Event` 的类型或事件的 `get_type()` 返回值；
    如果 waits 为空则继承 `matcher` 参数的事件响应器类型
- matcher: 所属的 `Matcher` 对象，如果不指定则使用当前上下文的 `Matcher`
- parameterless: 非参数类型依赖列表
- keep_session: 是否保持会话，即仅允许会话发起者响应

### 等待

可直接用 `Waiter.wait` 等待函数返回结果：

```python
resp = await check.wait(timeout=60, default=False)
```

或使用异步迭代器持续等待，直到满足结果才退出循环。适合多轮对话：

```python
async for resp in check(timeout=60, default=False):
    ...
```

参数：

- default: 超时时返回的默认值
- timeout: 等待超时时间

### 便捷函数

插件提供了一个 `prompt` 函数用于直接等待用户输入，适用于等待用户输入文本消息：

```python
from nonebot_plugin_waiter import prompt

resp = await prompt("xxxx", timeout=60)
```

## 示例

等待用户输入数字，超时时间为 60 秒，此时 waits 接收所有来自当前用户的消息事件。

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

    async for resp in check(timeout=60):
        if resp is None:
            await test.send("等待超时")
            break
        if not resp.isdigit():
            await test.send("请输入数字")
            continue
        await test.send(f"你输入了{resp}")
        break
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
