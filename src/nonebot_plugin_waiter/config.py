from pydantic import Field, BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    waiter_timeout: float = Field(120)
    """默认等待超时时间"""

    waiter_retry_prompt: str = Field("输入错误，请重新输入。剩余次数：{count}")
    """默认重试时的提示信息"""
