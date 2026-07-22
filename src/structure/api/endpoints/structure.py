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


def _resolve_video_path(video_path: str) -> str:
    """解析视频路径到容器内可访问的绝对路径。

    - 绝对路径（以 ``/`` 开头）→ 直接使用（宿主机路径 = 容器内路径，由 volume 映射保证）
    - 相对路径 → 拼接 ``data_base_path``（兼容旧模式，如 immich 路径）
    """
    if video_path.startswith("/"):
        return video_path
    return str(Path(settings.data_base_path) / video_path)


@router.post(
    "/structure",
    response_model=ResponseDTO[StructureResultDTO],
    summary="视频结构化",
    description="传入视频路径和场景边界，执行九宫格生成 + 结构化分析。"
    " video_path 支持宿主机绝对路径或相对于 data_base_path 的路径。",
)
async def structure_video(
    command: StructureCommand,
) -> ResponseDTO[StructureResultDTO]:
    """对视频执行结构化处理。

    - ``video_path`` 支持宿主机绝对路径（如 ``/data/immich/photos/v.mp4``）
      或相对 ``data_base_path`` 的路径。
    - 可传入 ``scenes`` 指定场景边界。
    - 返回结构包含场景列表和九宫格缩略图路径（相对于 cache_base_path）。
    """
    abs_path = _resolve_video_path(command.video_path)
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
    abs_path = _resolve_video_path(command.video_path)
    await video_service.clear_cache(abs_path)
    return ResponseDTO.ok(None)
