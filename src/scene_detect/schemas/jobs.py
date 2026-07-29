from pydantic import BaseModel, Field


class DetectJobRequest(BaseModel):
    """提交 scene-detect 异步任务的请求"""

    video_path: str = Field(description="视频文件路径")
    threshold: float | None = Field(default=None, description="场景检测阈值")
    max_scenes: int | None = Field(default=None, description="最大场景数")
    scale_width: int | None = Field(
        default=None, description="检测管道 scale 宽度，0=不缩放；默认用全局配置"
    )
    decode_threads: int | None = Field(
        default=None, description="ffmpeg 解码线程数，0=auto；默认用全局配置"
    )
    cache_enabled: bool = Field(
        default=False,
        description="是否复用相同视频未完成的 scene-detect job",
    )
