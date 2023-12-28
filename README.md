# nonebot-plugin-waiter

该插件提供一个 got-and-reject 会话控制的替代方案，可自由控制超时时间

## 安装

```shell
pip install nonebot-plugin-waiter
```

## 使用

```python
from nonebot import on_command
from nonebot.adapters import Event
from nonebot_plugin_waiter import waiter

test = on_command("test")

@test.handle()
async def _(event: Event):
    await test.send("请输入数字")

    @waiter(test)
    async def check(event1: Event):
        if event.get_session_id() == event1.get_session_id():
            return event1.get_plaintext()

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
