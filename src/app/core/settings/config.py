from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_env: str = Field("dev", description="运行环境，例如 dev/test/prod")
    app_title: str = Field("video-instruction", description="应用名称")
    app_version: str = Field("0.1.0", description="应用版本")
    app_port: int = Field(8000, description="服务端口")

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
