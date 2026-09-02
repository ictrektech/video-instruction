from pydantic import BaseModel, Field

from shared.jobs.schemas import JobStatusResponse


class ArtifactFileDTO(BaseModel):
    """artifact 单文件信息"""

    path: str
    size: int


class ArtifactDTO(BaseModel):
    """structure job 的 artifact 可下载清单（v2 增量）"""

    describe_status: str = Field(description="none | pending | succeeded | failed")
    total_bytes: int
    files: list[ArtifactFileDTO]


class StructureJobStatusResponse(JobStatusResponse):
    """structure job 状态响应（v2 增量：含 released 与 artifact 块）。"""

    released: bool = Field(default=False, description="staging 目录是否已不存在")
    artifact: ArtifactDTO | None = Field(
        default=None, description="可下载产物清单；未冻结/已释放时为 null"
    )


class SceneBoundaryInput(BaseModel):
    scene_index: int = 0
    start_frame: int
    end_frame: int
    start_time: float = 0.0
    end_time: float = 0.0


class StructureJobRequest(BaseModel):
    """提交 structure 异步任务的请求（两种传 scenes 方式二选一）。"""

    video_path: str = Field(description="视频文件路径，或 http(s):// 视频流 URL")

    # 方式 A：直接传 scenes
    scenes: list[SceneBoundaryInput] | None = Field(default=None, description="场景边界列表")

    # 方式 B：引用 detect job
    detect_job_id: str | None = Field(default=None, description="scene-detect job ID")

    # StructureCommand 参数
    frame_grid: bool = Field(default=True, description="是否生成场景拼图")
    grid_rows: int = Field(default=3, description="场景图片拼接行数")
    grid_cols: int = Field(default=3, description="场景图片拼接列数")
