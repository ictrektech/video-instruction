from __future__ import annotations

from pydantic import BaseModel, Field


class ModelConfig(BaseModel):
    """大模型配置"""

    base_url: str = Field(description="API 地址，如 https://api.openai.com/v1")
    api_key: str = Field(default="", description="API Key")
    model_name: str = Field(description="模型名称，如 gpt-4o / qwen2-vl-7b")
    max_concurrency: int = Field(default=5, description="最大并发数")
    request_timeout: int = Field(default=120, description="单次请求超时秒数")
