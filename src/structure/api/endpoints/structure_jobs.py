from __future__ import annotations

from logging import getLogger
from pathlib import Path

from fastapi import APIRouter

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.jobs import (
    build_job_status_response,
    enqueue_job,
    get_job,
    try_duplicate_job,
)
from shared.jobs.schemas import JobStatusResponse, JobSubmitResponse
from shared.schemas.common.response import ResponseDTO
from structure.core.settings import settings
from structure.schemas.jobs import StructureJobRequest
from structure.utils import resolve_video_path

logger = getLogger(__name__)

router = APIRouter()


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
    # 参数校验
    abs_path = resolve_video_path(req.video_path, settings.data_base_path)
    if not Path(abs_path).is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, abs_path)

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

    # 去重：相同 video_path 有未完成任务时复用
    dup = try_duplicate_job("structure", "$.video_path", abs_path)
    if dup:
        return ResponseDTO.ok(
            JobSubmitResponse(
                job_id=dup,
                status="queued",
                poll_url=f"/api/v2/video/structure/jobs/{dup}",
            )
        )

    # 构建 request data
    scenes_data = [s.model_dump() for s in req.scenes] if req.scenes else None

    request_data = {
        "video_path": abs_path,
        "scenes": scenes_data,
        "detect_job_id": req.detect_job_id,
        "frame_grid": req.frame_grid,
        "force": req.force,
        "grid_rows": req.grid_rows,
        "grid_cols": req.grid_cols,
    }

    # 原子化：创建 jobs 行 + enqueue Huey task
    from structure.services.tasks import run_structure

    task_kwargs = {k: v for k, v in request_data.items() if k != "video_path"}
    job_id = enqueue_job(
        "structure",
        request_data,
        run_structure.task_class,
        task_args=(abs_path,),
        task_kwargs=task_kwargs,
    )

    logger.info("提交 structure job: id=%s video=%s", job_id, abs_path)
    return ResponseDTO.ok(
        JobSubmitResponse(
            job_id=job_id,
            status="queued",
            poll_url=f"/api/v2/video/structure/jobs/{job_id}",
        )
    )


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
