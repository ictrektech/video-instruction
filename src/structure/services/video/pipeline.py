from __future__ import annotations

import asyncio
import tempfile
import time
from logging import getLogger
from pathlib import Path

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from shared.utils.video_hash import compute_video_hash
from structure.core.settings import settings
from structure.schemas.video import (
    SceneDTO,
    StructureCommand,
    StructureResultDTO,
    VideoMetadataSchema,
    WarningDTO,
)
from structure.services.video.cache import (
    get_cache_path,
    invalidate_cache_dir,
    load_cached_result,
    save_cached_result,
    scenes_match,
)
from structure.services.video.frame_extract import (
    extract_scene_grids,
    scene_bounds_to_dtos,
)
from structure.services.video.metadata import extract_metadata

logger = getLogger(__name__)


async def structure(
    cmd: StructureCommand,
    video_path: str,
    work_dir: str | None = None,
) -> StructureResultDTO:
    """视频结构化入口：提取元数据 → 九宫格生成。

    scenes 必须通过 API 传入，由 scene-detection 服务提供。

    Args:
        cmd: 结构化请求参数。
        video_path: 视频文件绝对路径。
        work_dir: 工作目录，默认使用 ``settings.video_work_dir``。
    """
    video_path_obj = Path(video_path)
    if not video_path_obj.is_file():
        raise ApiException(BusinessErrorCode.VIDEO_FILE_NOT_FOUND, str(video_path_obj))

    if not cmd.scenes:
        raise ApiException(
            BusinessErrorCode.COMMON_UNSUPPORTED_OPERATION,
            "缺少场景边界，请先调用 scene-detection 服务获取场景信息",
        )

    work_dir = work_dir or settings.video_work_dir
    Path(work_dir).mkdir(parents=True, exist_ok=True)
    call_work_dir = Path(tempfile.mkdtemp(dir=work_dir))

    started_at = time.time()
    stage_timings: dict[str, float] = {}
    warnings: list[WarningDTO] = []

    # ── Step 0: 计算视频 hash 并尝试缓存命中 ────────────────────────
    video_hash = await asyncio.to_thread(compute_video_hash, video_path)
    cache_dir = get_cache_path(video_hash, settings)
    if not cmd.force and cache_dir.is_dir():
        cached = await asyncio.to_thread(load_cached_result, cache_dir, settings.cache_base_path)
        if cached is not None and scenes_match(cmd.scenes, cached.scenes):
            cached.elapsed_sec = round(time.time() - started_at, 2)
            cached.stage_timings["total"] = cached.elapsed_sec
            logger.info("缓存命中: %s", video_path)
            return cached
        logger.info("缓存未命中，重新处理: %s", cache_dir)

    # miss / force：清旧产物，避免残留 grid 与过期描述
    await asyncio.to_thread(invalidate_cache_dir, cache_dir)

    # ── Step 1: 提取元数据 ──────────────────────────────────────────
    t0 = time.time()
    metadata = await asyncio.to_thread(extract_metadata, video_path)
    stage_timings["metadata"] = round(time.time() - t0, 3)

    # ── Step 2: 场景边界（从 API 传入）────────────────────────────────
    scene_bounds: list[tuple[int, int, float, float]] = [
        (s.start_frame, s.end_frame, s.start_time, s.end_time) for s in cmd.scenes
    ]
    logger.info("使用 API 传入的场景边界: %d 个场景", len(scene_bounds))

    # ── Step 3: 九宫格生成 ──────────────────────────────────────────
    scenes: list[SceneDTO] = []
    if cmd.frame_grid and scene_bounds:
        t0 = time.time()
        grid_results = await asyncio.to_thread(
            extract_scene_grids,
            video_path,
            scene_bounds,
            metadata,
            call_work_dir,
            settings.video_grid_tile_max_height,
            cmd.grid_rows,
            cmd.grid_cols,
            cache_dir,
        )
        for grid_item, _warnings in grid_results:
            scenes.append(grid_item)
            warnings.extend(_warnings)
        stage_timings["frame_grid"] = round(time.time() - t0, 3)
    elif scene_bounds:
        scenes = scene_bounds_to_dtos(scene_bounds)

    elapsed_sec = round(time.time() - started_at, 2)
    stage_timings["total"] = elapsed_sec

    result = StructureResultDTO(
        video_hash=video_hash,
        metadata=VideoMetadataSchema(
            video_path=cmd.video_path,
            fps=metadata["fps"],
            duration=metadata["duration"],
            width=metadata["width"],
            height=metadata["height"],
            codec=metadata["codec"],
            bitrate=metadata["bitrate"],
            has_audio=metadata["has_audio"],
            total_frames=metadata["total_frames"],
        ),
        grid_base_path=f"{settings.video_scenes_dir}/{video_hash}/grids/",
        scenes=scenes,
        warnings=warnings,
        stage_timings=stage_timings,
        elapsed_sec=elapsed_sec,
    )

    # ── Step 4: 写入缓存（fire-and-forget）───────────────────────────
    try:
        await asyncio.to_thread(save_cached_result, cache_dir, result)
    except Exception as exc:
        logger.warning("缓存写入失败: %s", exc)

    return result


async def clear_cache(video_path: str) -> None:
    """计算视频 SHA-256 并删除对应的缓存目录。"""
    video_hash = await asyncio.to_thread(compute_video_hash, video_path)
    cache_dir = get_cache_path(video_hash, settings)
    if not cache_dir.is_dir():
        logger.info("无缓存可清除: %s", video_hash)
        raise ApiException(BusinessErrorCode.VIDEO_CACHE_NOT_FOUND)
    await asyncio.to_thread(invalidate_cache_dir, cache_dir)
