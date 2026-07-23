from pydantic import BaseModel, Field


class DetectJobRequest(BaseModel):
    """提交 scene-detect 异步任务的请求"""

    video_path: str = Field(description="视频文件路径")
    threshold: float | None = Field(default=None, description="场景检测阈值")
    max_scenes: int | None = Field(default=None, description="最大场景数")
