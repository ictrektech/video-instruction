from __future__ import annotations

from logging import getLogger

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
from structure.schemas.description import DescribeSceneCommand

logger = getLogger(__name__)

router = APIRouter()


@router.post(
    "/describe/jobs",
    response_model=ResponseDTO[JobSubmitResponse],
    summary="提交场景描述异步任务",
    description="传入 video_hash，创建异步场景描述 job，返回 job_id 用于轮询。",
)
async def submit_describe_job(
    command: DescribeSceneCommand,
) -> ResponseDTO[JobSubmitResponse]:
    """提交场景描述异步任务。

    相同 video_hash 已有未完成任务（queued/running）时，直接返回现有 job 信息。
    """
    # 去重：相同 video_hash 有未完成任务时复用
    dup = try_duplicate_job("describe", "$.video_hash", command.video_hash)
    if dup:
        return ResponseDTO.ok(
            JobSubmitResponse(
                job_id=dup,
                status="queued",
                poll_url=f"/api/v2/video/describe/jobs/{dup}",
            )
        )

    request_data = command.model_dump()

    from structure.services.tasks import run_describe_scenes

    task_kwargs = {k: v for k, v in request_data.items() if k != "video_hash"}
    job_id = enqueue_job(
        "describe",
        request_data,
        run_describe_scenes.task_class,
        task_args=(command.video_hash,),
        task_kwargs=task_kwargs,
    )

    logger.info("提交 describe job: id=%s hash=%s", job_id, command.video_hash)
    return ResponseDTO.ok(
        JobSubmitResponse(
            job_id=job_id,
            status="queued",
            poll_url=f"/api/v2/video/describe/jobs/{job_id}",
        )
    )


@router.get(
    "/describe/jobs/{job_id}",
    response_model=ResponseDTO[JobStatusResponse],
    summary="查询场景描述任务状态",
    description="成功时 result 为 SceneDescriptionResult 的完整 dict。",
)
async def get_describe_job(job_id: str) -> ResponseDTO[JobStatusResponse]:
    """查询 describe 任务状态与结果。"""
    row = get_job(job_id)
    if row is None:
        raise ApiException(BusinessErrorCode.JOB_NOT_FOUND, f"job_id={job_id}")
    return ResponseDTO.ok(build_job_status_response(row))
