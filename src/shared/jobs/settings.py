from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class HueySettings(BaseSettings):
    """Huey 任务队列配置"""

    huey_db_path: str = Field("data/huey/huey.db", description="Huey + jobs 共用的 SQLite 文件路径")
    huey_workers: int = Field(4, description="Worker 并行线程数")
    job_ttl_days: int = Field(7, description="jobs 表 TTL 天数（0 关闭）")

    model_config = SettingsConfigDict(
        env_file=(".env",),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = HueySettings()
