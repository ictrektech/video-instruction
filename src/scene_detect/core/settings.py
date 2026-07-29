from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """场景识别服务配置"""

    app_title: str = Field("video-instruction - Scene Detection", description="应用名称")
    app_version: str = Field("0.1.0", description="应用版本")
    app_port: int = Field(8910, description="服务端口")
    app_env: str = Field("dev", description="运行环境，例如 dev/test/prod")

    log_level: str = Field("INFO", description="日志级别")
    log_config_path: str = Field("config/log_conf.yaml", description="日志配置路径")
    cors_origins: str = Field("*", description="CORS 允许的源，多个用逗号分隔")

    data_base_path: str = Field("/data/video-structured", description="视频文件基础路径前缀")
    video_scene_threshold: float = Field(27.0, description="场景检测阈值（越大越不敏感）")
    video_max_scenes: int = Field(200, description="最大场景数限制")
    video_pipe_read_timeout: int = Field(30, description="ffmpeg 管道单次读帧超时秒数")
    # 管道优化：scale=640 切点稳；threads=2 兼顾多 worker（见 docker-compose environment）
    video_detect_scale_width: int = Field(
        640,
        description="检测管道 scale 宽度，0=不缩放；推荐 640",
    )
    video_decode_threads: int = Field(
        2,
        description="ffmpeg -threads；1=保守，2~4=更快，0=auto",
    )

    model_config = SettingsConfigDict(
        env_file=("src/scene_detect/.env", ".env"),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )


settings = Settings()  # pyright: ignore[reportCallIssue]
