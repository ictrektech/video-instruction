from __future__ import annotations

from logging import getLogger

from fastapi import APIRouter, BackgroundTasks

from shared.callback import assert_callback_url_available
from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.schemas.common.response import ResponseDTO
from shared.task_status import TaskStatusDTO, create_task, get_task_status
from structure.core.settings import settings
from structure.schemas.video import (
    StructureCallbackCommand,
    StructureSubmitDTO,
)
from structure.services.video.callback import run_structure_callback_task
from structure.utils import resolve_video_path

logger = getLogger(__name__)

router = APIRouter()


@router.post(
    "/structure",
    response_model=ResponseDTO[StructureSubmitDTO],
    summary="提交视频结构化任务",
    description=(
        "传入视频路径、场景边界和 callback_url，后台执行结构化并通过 "
        "multipart/form-data 回调状态和结果。"
    ),
)
async def structure_video(
    command: StructureCallbackCommand,
    background_tasks: BackgroundTasks,
) -> ResponseDTO[StructureSubmitDTO]:
    """提交结构化任务，处理结果通过 callback 推送给调用方。"""
    assert_callback_url_available(str(command.callback_url))
    abs_path = resolve_video_path(command.video_path, settings.data_base_path)
    task = create_task(
        task_type="structure",
        asset_id=command.asset_id,
        request=command.model_dump(mode="json"),
    )
    background_tasks.add_task(run_structure_callback_task, task.task_id, command, abs_path)
    logger.info(
        "queued structure callback task: task_id=%s asset_id=%s",
        task.task_id,
        command.asset_id,
    )
    return ResponseDTO.ok(
        StructureSubmitDTO(
            task_id=task.task_id,
            asset_id=command.asset_id,
            status=task.status,
        )
    )


@router.get(
    "/structure/tasks/{task_id}",
    response_model=ResponseDTO[TaskStatusDTO],
    summary="查询视频结构化任务状态",
)
async def get_structure_task_status(task_id: str) -> ResponseDTO[TaskStatusDTO]:
    status = get_task_status(task_id)
    if status is None or status.task_type != "structure":
        raise ApiException(BusinessErrorCode.JOB_NOT_FOUND, f"task_id={task_id}")
    return ResponseDTO.ok(status)
