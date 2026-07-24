from __future__ import annotations

import asyncio
import time
from logging import getLogger
from pathlib import Path

from fastapi import APIRouter

from scene_detect.core.settings import settings
from scene_detect.schemas.scene import DetectRequest, DetectResult
from scene_detect.services.detector import detect_scenes
from scene_detect.utils import coalesce, resolve_video_path
from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.schemas.common.response import ResponseDTO

logger = getLogger(__name__)

router = APIRouter()


@router.post(
    "/detect",
    response_model=ResponseDTO[DetectResult],
    summary="场景识别",
    description="传入视频路径，使用 PySceneDetect 检测场景边界，返回场景开始/结束帧。",
)
async def detect_scene(
    command: DetectRequest,
) -> ResponseDTO[DetectResult]:
    """对视频执行场景识别。

    - ``video_path`` 为相对于 ``data_base_path`` 的路径（也支持绝对路径）。
    - 只检测场景边界，不进行任何结构化操作。
    - 返回场景列表（含 start_frame / end_frame / start_time / end_time）。
    """
    video_path = resolve_video_path(command.video_path, settings.data_base_path)
    if not Path(video_path).is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, video_path)

    started_at = time.time()
    boundaries, metadata, policy, warnings = await asyncio.to_thread(
        detect_scenes,
        video_path,
        command.threshold,
        command.max_scenes,
        scale_width=coalesce(command.scale_width, settings.video_detect_scale_width),
        decode_threads=coalesce(command.decode_threads, settings.video_decode_threads),
    )
    elapsed_sec = round(time.time() - started_at, 2)

    result = DetectResult(
        metadata=metadata,
        policy=policy,
        scenes=boundaries,
        warnings=warnings,
        elapsed_sec=elapsed_sec,
    )
    return ResponseDTO.ok(result)
