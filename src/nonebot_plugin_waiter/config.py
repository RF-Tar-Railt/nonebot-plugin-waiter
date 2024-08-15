from pydantic import Field, BaseModel


class Config(BaseModel):
    """Plugin Config Here"""

    waiter_timeout: float = Field(120)
    """默认等待超时时间"""

    waiter_retry_prompt: str = Field("输入错误，请重新输入。剩余次数：{count}")
    """默认重试时的提示信息"""

    waiter_timeout_prompt: str = Field("等待超时。")
    """默认超时时的提示信息"""

    waiter_limited_prompt: str = Field("重试次数已用完，输入失败。")
    """默认重试次数用完时的提示信息"""

    waiter_suggest_hint: str = Field("- {suggest}")
    """默认建议信息的提示"""

    waiter_suggest_sep: str = Field("\n")
    """默认建议信息的分隔符"""

    waiter_suggest_not_in_hint: str = Field("以下为非候选项")
    """默认非候选项前的提示信息"""
