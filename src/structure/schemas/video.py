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

    video_path: str = Field(
        description="视频文件路径（相对 data_base_path 或绝对路径），或 http(s):// 视频流 URL"
    )
    scenes: list[SceneBoundaryInput] = Field(
        description="场景边界列表，由 scene-detection 服务提供"
    )
    frame_grid: bool = Field(default=True, description="是否生成场景拼图")
    grid_rows: int = Field(default=3, description="场景图片拼接行数")
    grid_cols: int = Field(default=3, description="场景图片拼接列数")
    structure_job_id: str = Field(default="", description="structure job ID，用作 staging 目录名")


class CacheClearCommand(BaseModel):
    """清除缓存请求参数"""

    video_path: str = Field(
        description="视频文件路径（相对 data_base_path 或绝对路径），或 http(s):// 视频流 URL"
    )


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

    video_path: str = Field(description="视频文件路径或 http(s):// 视频流 URL，原样回传")
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

    video_hash: str = Field(description="视频身份哈希；URL 模式为脱敏 URL 的 SHA-256")
    metadata: VideoMetadataSchema = Field(description="视频元数据")
    staging_dir: str = Field(
        default="",
        description="本 job 产物暂存目录绝对路径，上游将其整体移动到自己的数据目录",
    )
    scenes: list[SceneDTO] = Field(description="场景列表")
    warnings: list[WarningDTO] = Field(default_factory=list, description="警告信息")
    stage_timings: dict[str, float] = Field(default_factory=dict, description="各阶段耗时(秒)")
    elapsed_sec: float = Field(default=0.0, description="总耗时(秒)")
