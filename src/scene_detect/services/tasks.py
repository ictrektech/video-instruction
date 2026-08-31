"""Huey 任务函数：scene-detect 异步执行。

任务函数自管理 jobs 表状态：
  queued → running → succeeded / failed

通过 @huey.task() 注册到 Huey registry，API 层可用
run_detect_scenes.task_class(id=..., args=..., kwargs=...) 创建 Task 并入队。
"""

from __future__ import annotations

import time
from logging import getLogger

from shared.jobs import huey, update_job
from shared.utils.video_source import redact_url

logger = getLogger(__name__)


@huey.task(context=True)
def run_detect_scenes(
    job_id: str,
    video_path: str,
    *,
    threshold: float | None = None,
    max_scenes: int | None = None,
    scale_width: int | None = None,
    decode_threads: int | None = None,
    task=None,  # injected by context=True
) -> list[dict]:
    """Huey 任务：执行场景检测并更新 jobs 状态。

    Args:
        job_id: jobs 表主键。
        video_path: 视频绝对路径。
        threshold: 场景检测阈值；None 使用时长策略。
        max_scenes: 最大场景数；None 使用时长策略，0 不限制。
        scale_width: 管道 scale 宽度覆盖；None 用 settings。
        decode_threads: 解码线程数覆盖；None 用 settings。
        task: Huey Task 实例（由 context=True 注入）。

    Returns:
        scenes 列表。
    """
    started_at = int(time.time())
    update_job(job_id, status="running", started_at=started_at, attempt=1)

    try:
        from scene_detect.services.detector import detect_scenes

        boundaries, metadata, policy, warnings = detect_scenes(
            video_path,
            threshold,
            max_scenes,
            scale_width=scale_width,
            decode_threads=decode_threads,
        )

        scenes = [
            {
                "scene_index": b.scene_index,
                "start_frame": b.start_frame,
                "end_frame": b.end_frame,
                "start_time": b.start_time,
                "end_time": b.end_time,
            }
            for b in boundaries
        ]

        finished_at = int(time.time())
        update_job(
            job_id,
            status="succeeded",
            finished_at=finished_at,
            result_json={
                "metadata": metadata.model_dump(mode="json"),
                "policy": policy.model_dump(mode="json"),
                "scenes": scenes,
                "warnings": [warning.model_dump(mode="json") for warning in warnings],
            },
        )

        logger.info(
            "scene-detect 完成: job=%s video=%s scenes=%d warnings=%d "
            "elapsed=%ds threshold=%s max_scenes=%s scale=%s decode_threads=%s",
            job_id,
            redact_url(video_path),
            len(scenes),
            len(warnings),
            finished_at - started_at,
            threshold,
            max_scenes,
            scale_width,
            decode_threads,
        )
        return scenes

    except Exception as exc:
        finished_at = int(time.time())
        update_job(
            job_id,
            status="failed",
            finished_at=finished_at,
            error_code="SCENE_DETECT_ERROR",
            error_message=redact_url(str(exc)),
        )
        logger.exception(
            "scene-detect 失败: job=%s video=%s err=%s threshold=%s "
            "max_scenes=%s scale=%s decode_threads=%s",
            job_id,
            redact_url(video_path),
            redact_url(str(exc)),
            threshold,
            max_scenes,
            scale_width,
            decode_threads,
        )
        raise


# Worker 通过 TASKS 显式引用本模块已注册的 task，避免 side-effect-only import
TASKS = (run_detect_scenes,)
