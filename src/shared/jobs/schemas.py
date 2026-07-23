"""共享的任务状态响应 DTO，统一 scene-detect 和 structure 的查询格式。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class JobSubmitResponse(BaseModel):
    """提交任务的响应（两服务共用）"""

    job_id: str
    status: str = "queued"
    poll_url: str


class JobErrorDTO(BaseModel):
    """任务错误信息（两服务共用）"""

    code: str | None = None
    message: str | None = None
    detail: str | None = None


class JobStatusResponse(BaseModel):
    """查询任务状态的响应（两服务共用）。

    result 为 dict | None，具体结构由 job_type 决定：
      - scene_detect: {"scenes": [...]}
      - structure:     StructureResultDTO 的完整 dict
    """

    job_id: str
    type: str
    status: str  # queued | running | succeeded | failed
    created_at: int | None = None
    started_at: int | None = None
    finished_at: int | None = None
    attempt: int = 0
    result: dict | None = Field(default=None, description="任务结果 dict，成功时非空")
    error: JobErrorDTO | None = None
