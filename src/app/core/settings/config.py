from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field("dev", description="运行环境，例如 dev/test/prod")
    app_title: str = Field("fastapi-template", description="应用名称")
    app_version: str = Field("0.1.0", description="应用版本")
    app_port: int = Field(8000, description="服务端口")

    db_url: str = Field(
        "postgresql+asyncpg://user:password@127.0.0.1:5432/mydatabase",
        description="数据库连接地址",
    )
    redis_url: str = Field("redis://127.0.0.1:6379/0", description="Redis 连接地址")

    jwt_secret: str = Field("change-me", description="JWT 签名密钥")
    jwt_expiration_seconds: int = Field(604800, description="JWT 过期秒数")

    rate_limit_default_permits: float = Field(10.0, description="默认限流令牌数")
    rate_limit_default_window_seconds: float = Field(1.0, description="默认限流时间窗秒数")
    log_level: str = Field("INFO", description="日志级别")
    log_config_path: str = Field("config/log_conf.yaml", description="日志配置路径")
    cors_origins: str = Field("*", description="CORS 允许的源，多个用逗号分隔")

    model_config = SettingsConfigDict(
        env_file=("src/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
