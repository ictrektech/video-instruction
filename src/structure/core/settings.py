from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """结构化服务配置"""

    app_title: str = Field("video-instruction - structure", description="应用名称")
    app_version: str = Field("0.1.0", description="应用版本")
    app_port: int = Field(8911, description="服务端口")
    app_env: str = Field("dev", description="运行环境，例如 dev/test/prod")

    log_level: str = Field("INFO", description="日志级别")
    log_config_path: str = Field("config/log_conf.yaml", description="日志配置路径")
    cors_origins: str = Field("*", description="CORS 允许的源，多个用逗号分隔")

    data_base_path: str = Field("/data", description="视频文件基础路径前缀（相对路径模式）")
    cache_base_path: str = Field(
        "/data/video-structure-cache", description="结构化输出缓存根目录（与输入解耦）"
    )
    video_work_dir: str = Field("/tmp/video-structured", description="视频处理临时工作目录")  # noqa: S108
    video_grid_tile_max_height: int = Field(360, description="九宫格单 tile 最大高度(像素)")
    video_grid_ffmpeg_threads: int = Field(0, description="九宫格取帧 ffmpeg -threads；0=auto，1=保守")
    video_scenes_dir: str = Field(
        "scenes",
        description="场景缓存持久化子目录名，相对于 cache_base_path",
    )

    # ── 大模型描述 ────────────────────────────────────────────
    llm_base_url: str = Field("http://localhost:13454/v1", description="LLM API 地址")
    llm_api_key: str = Field("", description="LLM API Key")
    llm_model_name: str = Field("qwen2-vl-7b", description="LLM 模型名称")
    llm_max_concurrency: int = Field(5, description="并发描述的场景数")
    llm_request_timeout: int = Field(120, description="单次 LLM 请求超时秒数")

    model_config = SettingsConfigDict(
        env_file=("src/structure/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
