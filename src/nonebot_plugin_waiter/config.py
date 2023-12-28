from pydantic import Extra, Field, BaseModel


class Config(BaseModel, extra=Extra.ignore):
    """Plugin Config Here"""

    waiter_timeout: float = Field(120)
    """默认等待超时时间"""
