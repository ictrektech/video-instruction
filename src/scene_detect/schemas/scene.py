from pydantic import BaseModel, Field


class SceneBoundary(BaseModel):
    """单场景边界 DTO"""

    scene_index: int = Field(description="场景序号（从 0 开始）")
    start_frame: int = Field(description="起始帧索引")
    end_frame: int = Field(description="结束帧索引")
    start_time: float = Field(description="开始时间(秒)")
    end_time: float = Field(description="结束时间(秒)")


class SceneMetadata(BaseModel):
    """场景检测所需的视频元信息"""

    fps: float = Field(description="帧率")
    total_frames: int = Field(description="总帧数")
    duration: float = Field(description="时长(秒)")
    width: int = Field(description="视频宽度(像素)")
    height: int = Field(description="视频高度(像素)")


class ScenePolicyDTO(BaseModel):
    """本次检测实际生效的策略参数"""

    threshold: float = Field(description="实际使用的场景检测阈值")
    min_scene_len_sec: float = Field(description="短场景合并阈值(秒)")
    max_scene_count: int = Field(description="实际使用的最大场景数")


class WarningDTO(BaseModel):
    """警告信息 DTO"""

    code: str = Field(description="警告代码")
    message: str = Field(description="警告描述")
    scope: str = Field(default="", description="警告作用域")
    target_id: str = Field(default="", description="目标标识")


class DetectRequest(BaseModel):
    """场景检测请求参数"""

    video_path: str = Field(
        description="视频文件路径（相对 data_base_path 或绝对路径），或 http(s):// 视频流 URL"
    )
    threshold: float | None = Field(default=None, description="场景检测阈值，默认使用全局配置")
    max_scenes: int | None = Field(default=None, description="最大场景数，默认使用全局配置")
    scale_width: int | None = Field(
        default=None, description="检测管道 scale 宽度，0=不缩放；默认用全局配置"
    )
    decode_threads: int | None = Field(
        default=None, description="ffmpeg 解码线程数，0=auto；默认用全局配置"
    )


class DetectResult(BaseModel):
    """场景检测结果"""

    metadata: SceneMetadata = Field(description="视频元信息")
    policy: ScenePolicyDTO = Field(description="本次检测实际生效的策略参数")
    scenes: list[SceneBoundary] = Field(description="场景边界列表")
    warnings: list[WarningDTO] = Field(default_factory=list, description="警告信息")
    elapsed_sec: float = Field(default=0.0, description="总耗时(秒)")
