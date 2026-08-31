from __future__ import annotations

from logging import getLogger
from pathlib import Path

from fastapi import APIRouter

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
from shared.utils.video_source import (
    is_http_url,
    redact_url,
    resolve_video_path,
    video_identity,
)
from structure.core.settings import settings
from structure.schemas.jobs import StructureJobRequest

logger = getLogger(__name__)

router = APIRouter()

_POLL_PREFIX = "/api/v2/video/structure/jobs"


@router.post(
    "/structure/jobs",
    response_model=ResponseDTO[JobSubmitResponse],
    summary="提交视频结构化异步任务",
    description="传入视频路径和场景边界（或 detect_job_id），创建异步 structure job。",
)
async def submit_structure_job(
    req: StructureJobRequest,
) -> ResponseDTO[JobSubmitResponse]:
    """提交 structure 异步任务。

    两种传 scenes 方式二选一：
      - scenes：直接传入场景边界列表
      - detect_job_id：引用 scene-detect job 的结果
    """
    media_path = resolve_video_path(req.video_path, settings.data_base_path)
    if not is_http_url(media_path) and not Path(media_path).is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, media_path)

    if not req.scenes and not req.detect_job_id:
        raise ApiException(
            BusinessErrorCode.COMMON_INVALID_ARGUMENT,
            "scenes 和 detect_job_id 至少提供一个",
        )

    if req.detect_job_id:
        detect_job = get_job(req.detect_job_id)
        if detect_job is None:
            raise ApiException(
                BusinessErrorCode.JOB_NOT_FOUND,
                f"detect_job_id={req.detect_job_id}",
            )

    video_hash = video_identity(media_path)

    existing = get_pending_job_by_video_hash("structure", video_hash)
    if existing:
        logger.info("structure job 已存在，复用: id=%s hash=%s", existing, video_hash)
        return ResponseDTO.ok(build_job_submit_response(existing, _POLL_PREFIX))

    scenes_data = [s.model_dump() for s in req.scenes] if req.scenes else None
    task_kwargs = {
        "scenes": scenes_data,
        "detect_job_id": req.detect_job_id,
        "frame_grid": req.frame_grid,
        "grid_rows": req.grid_rows,
        "grid_cols": req.grid_cols,
    }
    request_data = {"video_path": media_path, "video_hash": video_hash, **task_kwargs}

    from structure.services.tasks import run_structure

    job_id = enqueue_job(
        "structure",
        request_data,
        run_structure.task_class,
        task_args=(media_path,),
        task_kwargs=task_kwargs,
        video_hash=video_hash,
    )

    logger.info(
        "提交 structure job: id=%s hash=%s video=%s",
        job_id,
        video_hash,
        redact_url(media_path),
    )
    return ResponseDTO.ok(build_job_submit_response(job_id, _POLL_PREFIX))


@router.get(
    "/structure/jobs/{job_id}",
    response_model=ResponseDTO[JobStatusResponse],
    summary="查询视频结构化任务状态",
    description="成功时 result 为 StructureResultDTO 的完整 dict。",
)
async def get_structure_job(job_id: str) -> ResponseDTO[JobStatusResponse]:
    """查询 structure 任务状态与结果。"""
    row = get_job(job_id)
    if row is None:
        raise ApiException(BusinessErrorCode.JOB_NOT_FOUND, f"job_id={job_id}")
    return ResponseDTO.ok(build_job_status_response(row))
