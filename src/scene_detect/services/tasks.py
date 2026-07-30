from __future__ import annotations

import asyncio
import time
from logging import getLogger

from scene_detect.core.settings import settings
from scene_detect.schemas.scene import DetectResult, DetectTaskRequest
from scene_detect.services.detector import detect_scenes
from scene_detect.utils import coalesce
from shared.core.errors.exceptions import ApiException
from shared.task_status import set_task_status

logger = getLogger(__name__)


async def run_detect_task(command: DetectTaskRequest, video_path: str) -> None:
    try:
        set_task_status(
            command.task_id,
            task_type="scene_detect",
            asset_id=command.asset_id,
            status="running",
            stage="scene_detect",
            progress=0.0,
            message="scene detect task started",
        )

        started_at = time.time()
        boundaries, metadata, policy, warnings = await asyncio.to_thread(
            detect_scenes,
            video_path,
            command.threshold,
            None,
            scale_width=coalesce(command.scale_width, settings.video_detect_scale_width),
            decode_threads=coalesce(command.decode_threads, settings.video_decode_threads),
        )
        result = DetectResult(
            metadata=metadata,
            policy=policy,
            scenes=boundaries,
            warnings=warnings,
            elapsed_sec=round(time.time() - started_at, 2),
        )

        set_task_status(
            command.task_id,
            task_type="scene_detect",
            asset_id=command.asset_id,
            status="succeeded",
            stage="done",
            progress=1.0,
            message="scene detect task succeeded",
            result=result.model_dump(mode="json"),
        )
    except Exception as exc:
        logger.exception("scene detect task failed: task_id=%s", command.task_id)
        error = _error_payload(exc)
        set_task_status(
            command.task_id,
            task_type="scene_detect",
            asset_id=command.asset_id,
            status="failed",
            stage="scene_detect",
            message=str(exc),
            error=error,
        )


def _error_payload(exc: Exception) -> dict[str, str]:
    if isinstance(exc, ApiException):
        return {
            "code": str(exc.code),
            "message": exc.message,
            "detail": "",
        }
    return {
        "code": exc.__class__.__name__,
        "message": str(exc),
        "detail": "",
    }
