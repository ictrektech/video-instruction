from pydantic import BaseModel, Field


class SceneBoundaryInput(BaseModel):
    scene_index: int = 0
    start_frame: int
    end_frame: int
    start_time: float = 0.0
    end_time: float = 0.0


class StructureJobRequest(BaseModel):
    """提交 structure 异步任务的请求（两种传 scenes 方式二选一）。"""

    video_path: str = Field(description="视频文件路径")

    # 方式 A：直接传 scenes
    scenes: list[SceneBoundaryInput] | None = Field(default=None, description="场景边界列表")

    # 方式 B：引用 detect job
    detect_job_id: str | None = Field(default=None, description="scene-detect job ID")

    # StructureCommand 参数
    frame_grid: bool = Field(default=True, description="是否生成场景拼图")
    force: bool = Field(default=False, description="强制重新结构化")
    cache_enabled: bool = Field(default=True, description="是否启用结构化缓存读写")
    grid_rows: int = Field(default=3, description="场景图片拼接行数")
    grid_cols: int = Field(default=3, description="场景图片拼接列数")
