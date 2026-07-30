from __future__ import annotations

import asyncio
import shutil
import tempfile
from logging import getLogger
from pathlib import Path

from shared.callback import send_multipart_event
from shared.core.errors.exceptions import ApiException
from shared.task_status import set_task_status
from structure.core.settings import settings
from structure.schemas.video import (
    StructureCallbackCommand,
    StructureCallbackEvent,
)
from structure.services.video import pipeline

logger = getLogger(__name__)


async def run_structure_callback_task(command: StructureCallbackCommand, video_path: str) -> None:
    """Run structure processing and report every terminal state through callback."""
    Path(settings.video_work_dir).mkdir(parents=True, exist_ok=True)
    task_dir = Path(tempfile.mkdtemp(prefix=f"{command.task_id}_", dir=settings.video_work_dir))
    grid_dir = task_dir / "grids"
    callback_url = str(command.callback_url)

    try:
        await _send_event(
            callback_url,
            StructureCallbackEvent(
                task_id=command.task_id,
                asset_id=command.asset_id,
                status="running",
                stage="structure",
                progress=0.0,
                message="structure task started",
            ),
        )
        set_task_status(
            command.task_id,
            task_type="structure",
            asset_id=command.asset_id,
            status="running",
            stage="structure",
            progress=0.0,
            message="structure task started",
        )

        result = await pipeline.structure(command, video_path, grid_output_dir=grid_dir)
        result.grid_base_path = ""

        files = _build_grid_file_parts(result.scenes, grid_dir)
        await _send_event(
            callback_url,
            StructureCallbackEvent(
                task_id=command.task_id,
                asset_id=command.asset_id,
                status="succeeded",
                stage="done",
                progress=1.0,
                message="structure task succeeded",
                video_hash=result.video_hash,
                result=result,
            ),
            files=files,
        )
        set_task_status(
            command.task_id,
            task_type="structure",
            asset_id=command.asset_id,
            status="succeeded",
            stage="done",
            progress=1.0,
            message="structure task succeeded",
            result=result.model_dump(mode="json"),
        )
    except Exception as exc:
        logger.exception("structure callback task failed: task_id=%s", command.task_id)
        error = _error_payload(exc)
        set_task_status(
            command.task_id,
            task_type="structure",
            asset_id=command.asset_id,
            status="failed",
            stage="structure",
            message=str(exc),
            error=error,
        )
        await _send_event(
            callback_url,
            StructureCallbackEvent(
                task_id=command.task_id,
                asset_id=command.asset_id,
                status="failed",
                stage="structure",
                message=str(exc),
                error=error,
            ),
        )
    finally:
        await asyncio.to_thread(shutil.rmtree, task_dir, ignore_errors=True)


def _build_grid_file_parts(scenes, grid_dir: Path) -> list[tuple[str, str, bytes, str]]:
    files: list[tuple[str, str, bytes, str]] = []
    for scene in scenes:
        if scene.grid_image is None:
            continue
        path = grid_dir / scene.grid_image
        if not path.is_file():
            continue
        part_name = f"scene_{scene.scene_index + 1:03d}"
        files.append((part_name, scene.grid_image, path.read_bytes(), "image/jpeg"))
    return files


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


async def _send_event(
    callback_url: str,
    event: StructureCallbackEvent,
    files: list[tuple[str, str, bytes, str]] | None = None,
) -> None:
    await send_multipart_event(callback_url, event, files or [])
