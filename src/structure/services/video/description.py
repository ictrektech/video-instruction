from __future__ import annotations

import json
import logging
import tempfile
import time
from asyncio import Semaphore, gather
from pathlib import Path
from shutil import move

from pydantic import ValidationError

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException
from structure.core.settings import Settings
from structure.schemas.description import (
    SceneDescriptionItem,
    SceneDescriptionResult,
)
from structure.schemas.model_config import ModelConfig
from structure.schemas.video import WarningDTO
from structure.services.llm.client import LLMClient, LLMRequestError
from structure.services.video.cache import get_cache_path, load_cached_result

logger = logging.getLogger(__name__)


def _descriptions_cache_path(cache_dir: Path) -> Path:
    return cache_dir / "_descriptions.json"


def _load_cached_descriptions(cache_dir: Path) -> SceneDescriptionResult | None:
    """从缓存中读取已有描述结果"""
    path = _descriptions_cache_path(cache_dir)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return SceneDescriptionResult(**data)
    except (json.JSONDecodeError, ValidationError, OSError) as exc:
        logger.warning("描述缓存读取失败，将重新生成: %s", exc)
        return None


def _save_descriptions(cache_dir: Path, result: SceneDescriptionResult) -> None:
    """保存描述结果到缓存"""
    path = _descriptions_cache_path(cache_dir)
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
        move(tmp_path, path)
        logger.info("描述缓存已保存: %s", cache_dir)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


async def describe_scenes(
    video_hash: str,
    settings: Settings,
    model_cfg: ModelConfig | None,
    force: bool = False,
) -> SceneDescriptionResult:
    """对指定视频的所有场景进行大模型描述

    流程：
    1. 查找场景缓存，确认视频已结构化
    2. 如果已有描述缓存且非 force，直接返回
    3. 并发对各场景图片调用 LLM
    4. 保存描述缓存并返回

    Args:
        video_hash: 视频内容哈希
        settings: 服务配置
        llm_config: 大模型配置
        force: 是否强制重新描述（忽略缓存）

    Returns:
        场景描述结果

    Raises:
        ApiException: 场景缓存未找到时抛出
    """
    cache_dir = get_cache_path(video_hash, settings)

    # 1. 查找场景缓存
    cached_result = load_cached_result(cache_dir, settings.data_base_path)
    if cached_result is None:
        raise ApiException(BusinessErrorCode.VIDEO_SCENE_CACHE_MISS)

    # 2. 检查描述缓存
    if not force:
        cached_descriptions = _load_cached_descriptions(cache_dir)
        if cached_descriptions is not None:
            logger.info(
                "视频 %s 场景描述缓存命中: %s",
                video_hash,
                _descriptions_cache_path(cache_dir),
            )
            return cached_descriptions

    # 3. 构造图片路径 & 并发描述
    scenes = cached_result.scenes
    grids_dir = cache_dir / "grids"

    if model_cfg is None:
        raise ApiException(BusinessErrorCode.COMMON_INVALID_ARGUMENT, "缺少大模型配置")

    llm_client = LLMClient(
        base_url=model_cfg.base_url,
        api_key=model_cfg.api_key,
        model_name=model_cfg.model_name,
        timeout=model_cfg.request_timeout or settings.llm_request_timeout,
        trace_log=settings.llm_trace_log,
    )

    sem = Semaphore(model_cfg.max_concurrency)

    async def _describe_one(
        scene_index: int, grid_image: str
    ) -> tuple[SceneDescriptionItem, WarningDTO | None]:
        async with sem:
            image_path = grids_dir / grid_image
            if not image_path.is_file():
                logger.warning("场景 %d 图片不存在: %s", scene_index, image_path)
                return (
                    SceneDescriptionItem(
                        scene_index=scene_index,
                        grid_image=grid_image,
                        status="failed",
                        error="图片文件不存在",
                    ),
                    None,
                )

            try:
                description = await llm_client.describe_image(image_path, scene_index)
                return (
                    SceneDescriptionItem(
                        scene_index=scene_index,
                        grid_image=grid_image,
                        description=description,
                        status="ok",
                    ),
                    None,
                )
            except LLMRequestError as exc:
                msg = str(exc)
                logger.error("场景 %d 描述失败: %s", scene_index, msg)
                return (
                    SceneDescriptionItem(
                        scene_index=scene_index,
                        grid_image=grid_image,
                        status="failed",
                        error=msg,
                    ),
                    WarningDTO(
                        code="DESC_LLM_ERROR",
                        message=f"场景 {scene_index} 描述失败: {msg}",
                        scope="scene_description",
                        target_id=str(scene_index),
                    ),
                )

    start = time.monotonic()
    tasks = [_describe_one(s.scene_index, s.grid_image) for s in scenes if s.grid_image is not None]
    # 没有 grid_image 的场景标记为 skipped
    skipped: list[SceneDescriptionItem] = [
        SceneDescriptionItem(
            scene_index=s.scene_index,
            grid_image="",
            status="skipped",
        )
        for s in scenes
        if s.grid_image is None
    ]

    item_results: list[tuple[SceneDescriptionItem, WarningDTO | None]] = await gather(*tasks)
    results = [item for item, _ in item_results]
    warnings: list[WarningDTO] = [w for _, w in item_results if w is not None]
    results.extend(skipped)
    elapsed = time.monotonic() - start

    # 按 scene_index 排序
    results.sort(key=lambda x: x.scene_index)

    result = SceneDescriptionResult(
        video_hash=video_hash,
        descriptions=results,
        warnings=warnings,
    )

    # 5. 保存缓存
    _save_descriptions(cache_dir, result)

    logger.info(
        "场景描述完成: video_hash=%s, scenes=%d, elapsed=%.2fs",
        video_hash,
        len(results),
        elapsed,
    )
    return result
