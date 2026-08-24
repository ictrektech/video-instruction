from __future__ import annotations

from logging import getLogger

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
from structure.schemas.description import DescribeSceneCommand

logger = getLogger(__name__)

router = APIRouter()

_POLL_PREFIX = "/api/v2/video/describe/jobs"


@router.post(
    "/describe/jobs",
    response_model=ResponseDTO[JobSubmitResponse],
    summary="提交场景描述异步任务",
    description="传入 structure_job_id，创建异步场景描述 job，返回 job_id 用于轮询。",
)
async def submit_describe_job(
    command: DescribeSceneCommand,
) -> ResponseDTO[JobSubmitResponse]:
    """提交场景描述异步任务。

    相同 structure_job_id 已有未完成任务（queued/running）时，直接返回现有 job 信息。
    去重键用 structure_job_id（存入 jobs.video_hash 列，仅作去重，语义上代表"某份产物"）。
    """
    structure_job_id = command.structure_job_id

    existing = get_pending_job_by_video_hash("describe", structure_job_id)
    if existing:
        logger.info("describe job 已存在，复用: id=%s structure_job=%s", existing, structure_job_id)
        return ResponseDTO.ok(build_job_submit_response(existing, _POLL_PREFIX))

    from structure.services.tasks import run_describe_scenes

    request_data = command.model_dump()
    task_kwargs = {
        "force": command.force,
        "model_cfg": request_data.get("model_cfg"),
    }
    job_id = enqueue_job(
        "describe",
        request_data,
        run_describe_scenes.task_class,
        task_args=(structure_job_id,),
        task_kwargs=task_kwargs,
        video_hash=structure_job_id,
    )

    logger.info("提交 describe job: id=%s structure_job=%s", job_id, structure_job_id)
    return ResponseDTO.ok(build_job_submit_response(job_id, _POLL_PREFIX))


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
