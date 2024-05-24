from pydantic import Field, BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    waiter_timeout: float = Field(120)
    """默认等待超时时间"""
    waiter_count: int = Field(5)
    """默认等待次数"""
    waiter_msg: int = Field("输入错误,请重新输入 剩余次数{count}")
    """默认错误提示"""
