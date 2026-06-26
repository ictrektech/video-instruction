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

    data_base_path: str = Field("/data/video-structured", description="视频文件基础路径前缀")
    video_work_dir: str = Field("/tmp/video-structured", description="视频处理临时工作目录")  # noqa: S108
    video_ffmpeg_threads: int = Field(1, description="ffmpeg 内部线程数")
    video_grid_tile_max_height: int = Field(360, description="九宫格单 tile 最大高度(像素)")
    video_scenes_dir: str = Field(
        "scenes",
        description="场景缓存持久化子目录名，相对于 data_base_path",
    )

    model_config = SettingsConfigDict(
        env_file=("src/structure/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
