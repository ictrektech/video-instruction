from __future__ import annotations

from logging import getLogger
from pathlib import Path

from fastapi import APIRouter

from scene_detect.core.settings import settings as detect_settings
from scene_detect.schemas.jobs import DetectJobRequest
from scene_detect.utils import coalesce, resolve_video_path
from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.jobs import (
    build_job_status_response,
    build_job_submit_response,
    enqueue_job,
    get_job,
    get_pending_job_by_video_hash,
)
from shared.jobs.schemas import JobStatusResponse, JobSubmitResponse
from shared.schemas.common.response import ResponseDTO
from shared.utils.video_hash import compute_video_hash

logger = getLogger(__name__)

router = APIRouter()

_POLL_PREFIX = "/api/v2/scenes/detect/jobs"


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
    video_path = resolve_video_path(req.video_path, detect_settings.data_base_path)
    if not Path(video_path).is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, video_path)

    video_hash = compute_video_hash(video_path)

    existing = (
        get_pending_job_by_video_hash("scene_detect", video_hash) if req.cache_enabled else None
    )
    if existing:
        logger.info("scene_detect job 已存在，复用: id=%s hash=%s", existing, video_hash)
        return ResponseDTO.ok(build_job_submit_response(existing, _POLL_PREFIX))

    from scene_detect.services.tasks import run_detect_scenes

    task_kwargs = {
        "threshold": req.threshold,
        "max_scenes": req.max_scenes,
        "scale_width": coalesce(req.scale_width, detect_settings.video_detect_scale_width),
        "decode_threads": coalesce(req.decode_threads, detect_settings.video_decode_threads),
    }
    request_data = {
        "video_path": video_path,
        "video_hash": video_hash,
        "cache_enabled": req.cache_enabled,
        **task_kwargs,
    }
    job_id = enqueue_job(
        "scene_detect",
        request_data,
        run_detect_scenes.task_class,
        task_args=(video_path,),
        task_kwargs=task_kwargs,
        video_hash=video_hash if req.cache_enabled else None,
    )

    logger.info("提交 scene-detect job: id=%s hash=%s video=%s", job_id, video_hash, video_path)
    return ResponseDTO.ok(build_job_submit_response(job_id, _POLL_PREFIX))


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
