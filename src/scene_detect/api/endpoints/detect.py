from logging import getLogger
from pathlib import Path

from fastapi import APIRouter, BackgroundTasks

from scene_detect.core.settings import settings
from scene_detect.schemas.scene import DetectSubmitDTO, DetectTaskRequest
from scene_detect.services.tasks import run_detect_task
from scene_detect.utils import resolve_video_path
from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.schemas.common.response import ResponseDTO
from shared.task_status import TaskStatusDTO, get_task_status, set_task_status

logger = getLogger(__name__)

router = APIRouter()


@router.post(
    "/detect",
    response_model=ResponseDTO[DetectSubmitDTO],
    summary="提交场景检测任务",
    description="传入视频路径，后台检测场景边界；通过任务状态查询接口获取结果。",
)
async def detect_scene(
    command: DetectTaskRequest,
    background_tasks: BackgroundTasks,
) -> ResponseDTO[DetectSubmitDTO]:
    """提交场景检测任务，处理结果通过任务状态查询接口获取。"""
    video_path = resolve_video_path(command.video_path, settings.data_base_path)
    if not Path(video_path).is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, video_path)

    set_task_status(
        command.task_id,
        task_type="scene_detect",
        asset_id=command.asset_id,
        status="accepted",
        stage="accepted",
        progress=0.0,
        message="scene detect task accepted",
    )
    background_tasks.add_task(run_detect_task, command, video_path)
    logger.info(
        "accepted scene detect task: task_id=%s asset_id=%s",
        command.task_id,
        command.asset_id,
    )
    return ResponseDTO.ok(
        DetectSubmitDTO(
            task_id=command.task_id,
            asset_id=command.asset_id,
            status="accepted",
        )
    )


@router.get(
    "/detect/tasks/{task_id}",
    response_model=ResponseDTO[TaskStatusDTO],
    summary="查询场景检测任务状态",
)
async def get_detect_task_status(task_id: str) -> ResponseDTO[TaskStatusDTO]:
    status = get_task_status(task_id)
    if status is None or status.task_type != "scene_detect":
        raise ApiException(BusinessErrorCode.JOB_NOT_FOUND, f"task_id={task_id}")
    return ResponseDTO.ok(status)
