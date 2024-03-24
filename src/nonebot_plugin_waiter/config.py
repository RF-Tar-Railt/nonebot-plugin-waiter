from pydantic import Field, BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    waiter_timeout: float = Field(120)
    """默认等待超时时间"""
