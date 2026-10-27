from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """结构化服务配置"""

    app_title: str = Field("video-structure", description="应用名称")
    app_version: str = Field("0.1.0", description="应用版本")
    app_port: int = Field(8911, description="服务端口")
    app_env: str = Field("dev", description="运行环境，例如 dev/test/prod")

    log_level: str = Field("INFO", description="日志级别")
    log_config_path: str = Field("config/log_conf.yaml", description="日志配置路径")
    cors_origins: str = Field("*", description="CORS 允许的源，多个用逗号分隔")

    data_base_path: str = Field("/data", description="视频文件基础路径前缀（相对路径模式）")
    staging_base_path: str = Field(
        "/data/video-structure-cache",
        description="结构化产物暂存根目录（共享卷，上游搬走后即归上游所有）",
    )
    staging_ttl_sec: int = Field(
        6 * 3600,
        description="staging 目录 TTL 秒数；超过该时间未被上游搬走的产物会被清理",
    )
    video_work_dir: str = Field("/tmp/video-structured", description="视频处理临时工作目录")  # noqa: S108
    video_grid_tile_max_height: int = Field(360, description="九宫格单 tile 最大高度(像素)")
    video_grid_ffmpeg_threads: int = Field(
        0, description="九宫格取帧 ffmpeg -threads；0=auto，1=保守"
    )

    # ── 大模型描述 ────────────────────────────────────────────
    # 默认走同 VOS 内的 V-Scheduler 统一模型网关（compose 服务名 v-scheduler）
    llm_base_url: str = Field("http://v-scheduler:8080/v1", description="LLM API 地址")
    llm_api_key: str = Field("", description="LLM API Key；V-Scheduler 免验证模式下保持空串")
    llm_model_name: str = Field(
        "v-scheduler/ollama-qa/minicpm-v4.6:latest",
        description="LLM 模型名称（V-Scheduler 网关模型名，形如 v-scheduler/<来源>/<模型>:<标签>）",
    )
    llm_max_concurrency: int = Field(5, description="并发描述的场景数")
    llm_request_timeout: int = Field(120, description="单次 LLM 请求超时秒数")

    model_config = SettingsConfigDict(
        env_file=("src/structure/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
