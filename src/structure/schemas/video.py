from pydantic import BaseModel, Field


class SceneBoundaryInput(BaseModel):
    """传入的场景边界（与 scene-detection 服务输出格式一致）"""

    scene_index: int = Field(default=0, description="场景序号（从 0 开始）")
    start_frame: int = Field(description="起始帧索引")
    end_frame: int = Field(description="结束帧索引")
    start_time: float = Field(default=0.0, description="开始时间(秒)")
    end_time: float = Field(default=0.0, description="结束时间(秒)")


class StructureCommand(BaseModel):
    """视频结构化请求参数"""

    video_path: str = Field(description="视频文件路径，相对于 data_base_path")
    scenes: list[SceneBoundaryInput] = Field(
        description="场景边界列表，由 scene-detection 服务提供"
    )
    frame_grid: bool = Field(default=True, description="是否生成九宫格")
    force: bool = Field(default=False, description="强制重新结构化，忽略缓存")


class CacheClearCommand(BaseModel):
    """清除缓存请求参数"""

    video_path: str = Field(description="视频文件路径，相对于 data_base_path")


class SceneDTO(BaseModel):
    """场景输出 DTO"""

    scene_id: str = Field(description="场景 ID")
    scene_index: int = Field(description="场景序号（从 0 开始）")
    start_time: float = Field(description="开始时间(秒)")
    end_time: float = Field(description="结束时间(秒)")
    start_frame: int = Field(description="起始帧索引")
    end_frame: int = Field(description="结束帧索引")
    grid_image: str | None = Field(default=None, description="九宫格 JPEG 文件名，如 scene_001.jpg")


class VideoMetadataSchema(BaseModel):
    """视频元数据 DTO"""

    video_path: str = Field(description="视频文件路径")
    fps: float = Field(default=0.0, description="帧率")
    duration: float = Field(default=0.0, description="时长(秒)")
    width: int = Field(default=0, description="视频宽度(像素)")
    height: int = Field(default=0, description="视频高度(像素)")
    codec: str = Field(default="", description="视频编码格式")
    bitrate: int = Field(default=0, description="比特率(bps)")
    has_audio: bool = Field(default=False, description="是否包含音频流")
    total_frames: int = Field(default=0, description="总帧数")


class WarningDTO(BaseModel):
    """警告信息 DTO"""

    code: str = Field(description="警告代码")
    message: str = Field(description="警告描述")
    scope: str = Field(default="", description="警告作用域")
    target_id: str = Field(default="", description="目标标识")


class StructureResultDTO(BaseModel):
    """结构化结果 DTO"""

    video_id: str = Field(description="视频 ID")
    metadata: VideoMetadataSchema = Field(description="视频元数据")
    grid_base_path: str = Field(
        default="",
        description="九宫格图片基础路径(相对于 data_base_path)，与 scene.grid_image 拼接",
    )
    scenes: list[SceneDTO] = Field(description="场景列表")
    warnings: list[WarningDTO] = Field(default_factory=list, description="警告信息")
    stage_timings: dict[str, float] = Field(default_factory=dict, description="各阶段耗时(秒)")
    elapsed_sec: float = Field(default=0.0, description="总耗时(秒)")
