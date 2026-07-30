from __future__ import annotations

import time
from threading import Lock
from typing import Any

from pydantic import BaseModel, Field


class TaskStatusDTO(BaseModel):
    """In-process task status for dev async APIs."""

    task_id: str = Field(description="调用方任务 ID")
    asset_id: str = Field(default="", description="调用方资产 ID")
    task_type: str = Field(description="任务类型")
    status: str = Field(description="任务状态: accepted/running/succeeded/failed")
    stage: str = Field(default="", description="当前阶段")
    progress: float | None = Field(default=None, description="任务进度，0-1")
    message: str = Field(default="", description="状态消息")
    error: dict[str, str] | None = Field(default=None, description="失败信息")
    result: dict[str, Any] | None = Field(default=None, description="成功结果，不包含二进制文件")
    created_at: int = Field(description="创建时间 Unix 秒时间戳")
    updated_at: int = Field(description="更新时间 Unix 秒时间戳")


_TASKS: dict[str, TaskStatusDTO] = {}
_LOCK = Lock()


def set_task_status(
    task_id: str,
    *,
    task_type: str,
    asset_id: str = "",
    status: str,
    stage: str = "",
    progress: float | None = None,
    message: str = "",
    error: dict[str, str] | None = None,
    result: dict[str, Any] | None = None,
) -> TaskStatusDTO:
    now = int(time.time())
    with _LOCK:
        current = _TASKS.get(task_id)
        dto = TaskStatusDTO(
            task_id=task_id,
            asset_id=asset_id or (current.asset_id if current else ""),
            task_type=task_type,
            status=status,
            stage=stage,
            progress=progress,
            message=message,
            error=error,
            result=result,
            created_at=current.created_at if current else now,
            updated_at=now,
        )
        _TASKS[task_id] = dto
        return dto


def get_task_status(task_id: str) -> TaskStatusDTO | None:
    with _LOCK:
        return _TASKS.get(task_id)
