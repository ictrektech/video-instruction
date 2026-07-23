from __future__ import annotations

from logging import getLogger
from pathlib import Path

from fastapi import APIRouter

from scene_detect.core.settings import settings as detect_settings
from scene_detect.schemas.jobs import DetectJobRequest
from scene_detect.utils import resolve_video_path as resolve_detect_video_path
from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.jobs import build_job_status_response, enqueue_job, get_job
from shared.jobs.schemas import JobStatusResponse, JobSubmitResponse
from shared.schemas.common.response import ResponseDTO

logger = getLogger(__name__)

router = APIRouter()


@router.post(
    "/detect/jobs",
    response_model=ResponseDTO[JobSubmitResponse],
    summary="提交场景检测异步任务",
    description="传入视频路径，创建异步 scene-detect job，返回 job_id 用于轮询。",
)
async def submit_detect_job(
    req: DetectJobRequest,
) -> ResponseDTO[JobSubmitResponse]:
    """提交 scene-detect 异步任务。"""
    # 验证 video_path
    video_path = resolve_detect_video_path(req.video_path, detect_settings.data_base_path)
    if not Path(video_path).is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, video_path)

    threshold = (
        req.threshold if req.threshold is not None else detect_settings.video_scene_threshold
    )
    max_scenes = req.max_scenes if req.max_scenes is not None else detect_settings.video_max_scenes

    # 原子化：创建 jobs 行 + enqueue Huey task
    request_data = {
        "video_path": video_path,
        "threshold": threshold,
        "max_scenes": max_scenes,
    }
    from scene_detect.services.tasks import run_detect_scenes

    task_kwargs = {k: v for k, v in request_data.items() if k != "video_path"}
    job_id = enqueue_job(
        "scene_detect",
        request_data,
        run_detect_scenes.task_class,
        task_args=(video_path,),
        task_kwargs=task_kwargs,
    )

    logger.info("提交 scene-detect job: id=%s video=%s", job_id, video_path)
    return ResponseDTO.ok(
        JobSubmitResponse(
            job_id=job_id,
            status="queued",
            poll_url=f"/api/v2/scenes/detect/jobs/{job_id}",
        )
    )


@router.get(
    "/detect/jobs/{job_id}",
    response_model=ResponseDTO[JobStatusResponse],
    summary="查询场景检测任务状态",
)
async def get_detect_job(job_id: str) -> ResponseDTO[JobStatusResponse]:
    """查询 scene-detect 任务状态与结果。"""
    row = get_job(job_id)
    if row is None:
        raise ApiException(BusinessErrorCode.JOB_NOT_FOUND, f"job_id={job_id}")
    return ResponseDTO.ok(build_job_status_response(row))
