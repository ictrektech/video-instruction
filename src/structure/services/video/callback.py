from __future__ import annotations

import asyncio
import json
import shutil
import tempfile
from logging import getLogger
from pathlib import Path
from urllib.error import URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from shared.core.errors.exceptions import ApiException
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
    except Exception as exc:
        logger.exception("structure callback task failed: task_id=%s", command.task_id)
        await _send_event(
            callback_url,
            StructureCallbackEvent(
                task_id=command.task_id,
                asset_id=command.asset_id,
                status="failed",
                stage="structure",
                message=str(exc),
                error=_error_payload(exc),
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
    body, content_type = _encode_multipart(event, files or [])
    await asyncio.to_thread(_post_multipart, callback_url, body, content_type)


def _post_multipart(callback_url: str, body: bytes, content_type: str) -> None:
    request = Request(  # noqa: S310
        callback_url,
        data=body,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            if response.status >= 400:
                raise RuntimeError(f"callback failed with HTTP {response.status}")
    except URLError as exc:
        raise RuntimeError(f"callback request failed: {exc}") from exc


def _encode_multipart(
    event: StructureCallbackEvent,
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"video_instruction_{uuid4().hex}"
    chunks: list[bytes] = []

    def add(value: str | bytes) -> None:
        chunks.append(value.encode("utf-8") if isinstance(value, str) else value)

    event_json = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
    add(f"--{boundary}\r\n")
    add('Content-Disposition: form-data; name="event"\r\n')
    add("Content-Type: application/json; charset=utf-8\r\n\r\n")
    add(event_json)
    add("\r\n")

    for field_name, filename, data, content_type in files:
        add(f"--{boundary}\r\n")
        add(
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        )
        add(f"Content-Type: {content_type}\r\n\r\n")
        add(data)
        add("\r\n")

    add(f"--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"
