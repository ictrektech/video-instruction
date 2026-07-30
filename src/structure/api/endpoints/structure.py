from __future__ import annotations

from logging import getLogger

from fastapi import APIRouter, BackgroundTasks

from shared.schemas.common.response import ResponseDTO
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
    abs_path = resolve_video_path(command.video_path, settings.data_base_path)
    background_tasks.add_task(run_structure_callback_task, command, abs_path)
    logger.info(
        "accepted structure callback task: task_id=%s asset_id=%s",
        command.task_id,
        command.asset_id,
    )
    return ResponseDTO.ok(
        StructureSubmitDTO(
            task_id=command.task_id,
            asset_id=command.asset_id,
            status="accepted",
        )
    )
