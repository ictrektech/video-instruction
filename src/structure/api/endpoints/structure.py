from __future__ import annotations

from logging import getLogger
from pathlib import Path

from fastapi import APIRouter

from shared.schemas.common.response import ResponseDTO
from structure.core.settings import settings
from structure.schemas.video import (
    CacheClearCommand,
    StructureCommand,
    StructureResultDTO,
)
from structure.services.video import pipeline as video_service

logger = getLogger(__name__)

router = APIRouter()


@router.post(
    "/structure",
    response_model=ResponseDTO[StructureResultDTO],
    summary="视频结构化",
    description="传入视频路径和场景边界，执行场景检测（可选） + 九宫格生成，返回结构化结果。",
)
async def structure_video(
    command: StructureCommand,
) -> ResponseDTO[StructureResultDTO]:
    """对视频执行结构化处理。

    - ``video_path`` 为相对于 ``data_base_path`` 的路径。
    - 可传入 ``scenes`` 指定场景边界，不传则内部自动检测。
    - 返回结构包含场景列表和九宫格缩略图路径（相对于 data_base_path）。
    """
    abs_path = str(Path(settings.data_base_path) / command.video_path)
    dto = await video_service.structure(command, abs_path)
    return ResponseDTO.ok(dto)


@router.delete(
    "/cache",
    summary="清除视频缓存",
    description="根据视频路径计算 SHA-256，删除对应的缓存目录。",
)
async def delete_cache(
    command: CacheClearCommand,
) -> ResponseDTO[None]:
    """清除指定视频的缓存（九宫格图片缓存元数据）。"""
    abs_path = str(Path(settings.data_base_path) / command.video_path)
    await video_service.clear_cache(abs_path)
    return ResponseDTO.ok(None)
