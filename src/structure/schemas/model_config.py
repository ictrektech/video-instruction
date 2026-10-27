from __future__ import annotations

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """大模型配置。

    全部字段可缺省：请求体允许只传部分字段（如仅 max_concurrency），
    缺省字段回落到服务端 settings 默认值（默认指向 V-Scheduler 网关）。
    """

    base_url: str | None = Field(default=None, description="API 地址，如 https://api.openai.com/v1")
    api_key: str | None = Field(default=None, description="API Key")
    model_name: str | None = Field(default=None, description="模型名称，如 gpt-4o / qwen2-vl-7b")
    max_concurrency: int | None = Field(default=None, description="最大并发数")
    request_timeout: int | None = Field(default=None, description="单次请求超时秒数")
