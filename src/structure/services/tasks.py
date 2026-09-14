"""Huey 任务函数：structure 异步执行。

任务函数自管理 jobs 表状态：
  queued → running → succeeded / failed
"""

from __future__ import annotations

import asyncio
import json
import time
from logging import getLogger

from shared.jobs import get_job, huey, update_job
from shared.utils.video_source import redact_url

logger = getLogger(__name__)


def _get_scenes_from_detect_job(detect_job_id: str) -> list[dict]:
    """从 scene-detect job 的结果中读取 scenes。"""
    row = get_job(detect_job_id)
    if row is None:
        raise ValueError(f"detect_job not found: {detect_job_id}")
    if row["status"] != "succeeded":
        raise ValueError(f"detect_job not succeeded: {detect_job_id} status={row['status']}")
    if not row["result_json"]:
        raise ValueError(f"detect_job has no result: {detect_job_id}")

    try:
        data = json.loads(row["result_json"])
        return data.get("scenes", [])
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError(f"detect_job result_json parse failed: {exc}") from exc


@huey.task(context=True)
def run_structure(
    job_id: str,
    video_path: str,
    *,
    scenes: list[dict] | None = None,
    detect_job_id: str | None = None,
    frame_grid: bool = True,
    grid_rows: int = 3,
    grid_cols: int = 3,
    task=None,  # injected by context=True
) -> dict:
    """Huey 任务：执行视频结构化并更新 jobs 状态。

    Args:
        job_id: jobs 表主键（同时用作 staging 目录名）。
        video_path: 视频绝对路径。
        scenes: 直接传入的场景列表。
        detect_job_id: 引用的 scene-detect job ID（与 scenes 二选一）。
        frame_grid: 是否生成九宫格。
        grid_rows: 九宫格行数。
        grid_cols: 九宫格列数。
        task: Huey Task 实例（由 context=True 注入）。

    Returns:
        StructureResultDTO dict。
    """
    started_at = int(time.time())
    update_job(job_id, status="running", started_at=started_at, attempt=1)
    logger.info("structure 开始: job=%s video=%s", job_id, redact_url(video_path))

    try:
        # 解析 scenes
        resolved_scenes = scenes
        if detect_job_id:
            resolved_scenes = _get_scenes_from_detect_job(detect_job_id)
        if not resolved_scenes:
            raise ValueError("scenes is empty, provide scenes or detect_job_id")

        # 构建 StructureCommand
        from structure.schemas.video import SceneBoundaryInput, StructureCommand

        cmd = StructureCommand(
            video_path=video_path,
            scenes=[SceneBoundaryInput(**s) for s in resolved_scenes],
            frame_grid=frame_grid,
            grid_rows=grid_rows,
            grid_cols=grid_cols,
            structure_job_id=job_id,
        )

        # 调用 pipeline
        from structure.services.video import pipeline as video_pipeline

        result = asyncio.run(video_pipeline.structure(cmd, video_path))

        # 构建 result_ref（describe 通过它定位 staging 目录）
        ref_data = {
            "video_hash": result.video_hash,
            "staging_dir": result.staging_dir,
        }

        finished_at = int(time.time())
        update_job(
            job_id,
            status="succeeded",
            finished_at=finished_at,
            result_json=result.model_dump(mode="json"),
            result_ref=ref_data,
        )

        logger.info(
            "structure 完成: job=%s hash=%s scenes=%d elapsed=%ds",
            job_id,
            result.video_hash,
            len(result.scenes),
            finished_at - started_at,
        )
        return result.model_dump()

    except Exception as exc:
        finished_at = int(time.time())
        update_job(
            job_id,
            status="failed",
            finished_at=finished_at,
            error_code="STRUCTURE_ERROR",
            error_message=redact_url(str(exc)),
        )
        logger.exception("structure 失败: job=%s err=%s", job_id, redact_url(str(exc)))
        raise


@huey.task(context=True)
def run_describe_scenes(
    job_id: str,
    structure_job_id: str,
    *,
    force: bool = False,
    model_cfg: dict | None = None,
    task=None,  # injected by context=True
) -> dict:
    """Huey 任务：执行场景描述并更新 jobs 状态。

    Args:
        job_id: jobs 表主键。
        structure_job_id: 对应 structure job ID（describe 按其 staging 目录读取 grids）。
        force: 是否强制重新描述。
        model_cfg: 大模型配置 dict（ModelConfig.model_dump()），None 则使用服务端默认。
        task: Huey Task 实例（由 context=True 注入）。

    Returns:
        SceneDescriptionResult dict。
    """
    started_at = int(time.time())
    update_job(job_id, status="running", started_at=started_at, attempt=1)
    logger.info("describe 开始: job=%s structure_job=%s", job_id, structure_job_id)

    try:
        from structure.core.settings import settings as struct_settings
        from structure.schemas.model_config import ModelConfig
        from structure.services.video import description as description_service

        cfg = ModelConfig(**model_cfg) if model_cfg else None
        result = asyncio.run(
            description_service.describe_scenes(
                structure_job_id=structure_job_id,
                settings=struct_settings,
                model_cfg=cfg,
                force=force,
                progress_cb=lambda done, total: update_job(job_id, progress=f"{done}/{total}"),
            )
        )

        finished_at = int(time.time())
        update_job(
            job_id,
            status="succeeded",
            finished_at=finished_at,
            result_json=result.model_dump(mode="json"),
        )

        logger.info(
            "describe 完成: job=%s structure_job=%s scenes=%d elapsed=%ds",
            job_id,
            structure_job_id,
            len(result.descriptions),
            finished_at - started_at,
        )
        return result.model_dump()

    except Exception as exc:
        finished_at = int(time.time())
        update_job(
            job_id,
            status="failed",
            finished_at=finished_at,
            error_code="DESCRIBE_ERROR",
            error_message=str(exc),
        )
        logger.exception("describe 失败: job=%s", job_id)
        raise


# Worker 通过 TASKS 显式引用本模块已注册的 task，避免 side-effect-only import
TASKS = (run_structure, run_describe_scenes)
