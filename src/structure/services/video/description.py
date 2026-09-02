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
from shared.jobs import get_job
from structure.core.settings import Settings
from structure.schemas.description import (
    SceneDescriptionItem,
    SceneDescriptionResult,
)
from structure.schemas.model_config import ModelConfig
from structure.schemas.video import SceneDTO, WarningDTO
from structure.services.llm.client import LLMClient, LLMRequestError
from structure.services.video.cache import (
    get_descriptions_path,
    get_grids_dir,
    load_manifest,
    load_scenes,
    staging_dir_from_row,
)

logger = logging.getLogger(__name__)


def _resolve_staging_dir(structure_job_id: str) -> Path:
    """从 structure job 的 result_ref 解析 staging 目录绝对路径。"""
    row = get_job(structure_job_id)
    if row is None:
        raise ApiException(
            BusinessErrorCode.STRUCTURE_JOB_NOT_FOUND,
            f"structure_job_id={structure_job_id}",
        )
    if row["status"] != "succeeded":
        raise ApiException(
            BusinessErrorCode.STRUCTURE_JOB_NOT_SUCCEEDED,
            f"structure_job_id={structure_job_id} status={row['status']}",
        )

    staging_dir = staging_dir_from_row(row)
    if staging_dir is None:
        raise ApiException(
            BusinessErrorCode.STRUCTURE_JOB_NOT_SUCCEEDED,
            f"structure_job result_ref 缺少 staging_dir: {structure_job_id}",
        )
    return staging_dir


def _load_cached_descriptions(staging_dir: Path) -> SceneDescriptionResult | None:
    """从 staging 目录读取已有描述结果"""
    path = get_descriptions_path(staging_dir)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return SceneDescriptionResult(**data)
    except (json.JSONDecodeError, ValidationError, OSError) as exc:
        logger.warning("描述缓存读取失败，将重新生成: %s", exc)
        return None


def _save_descriptions(staging_dir: Path, result: SceneDescriptionResult) -> None:
    """保存描述结果到 staging 目录"""
    path = get_descriptions_path(staging_dir)
    fd, tmp_path = tempfile.mkstemp(dir=staging_dir, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(result.model_dump(), f, ensure_ascii=False, indent=2)
        move(tmp_path, path)
        logger.info("描述已保存: %s", staging_dir)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


def _descriptions_match_scenes(
    descriptions: SceneDescriptionResult,
    scenes: list[SceneDTO],
) -> bool:
    """描述缓存是否与当前 staging scenes 的 index 集合一致。"""
    return {item.scene_index for item in descriptions.descriptions} == {
        scene.scene_index for scene in scenes
    }


async def describe_scenes(
    structure_job_id: str,
    settings: Settings,
    model_cfg: ModelConfig | None,
    force: bool = False,
) -> SceneDescriptionResult:
    """对指定 structure job 的所有场景进行大模型描述

    流程：
    1. 通过 structure job 的 result_ref 找到 staging 目录
    2. 从 staging manifest 恢复 scenes，读取九宫格图片
    3. 如果已有描述且与当前 scenes 对齐、非 force，直接返回
    4. 并发对各场景图片调用 LLM
    5. 将描述写入 staging 目录的 descriptions.json

    Args:
        structure_job_id: 对应 structure job ID（其成功产物在 staging 目录）。
        settings: 服务配置。
        model_cfg: 大模型配置。
        force: 是否强制重新描述（忽略已有描述）。

    Returns:
        场景描述结果
    """
    # 1. 定位 staging 目录
    staging_dir = _resolve_staging_dir(structure_job_id)

    # 2. 从 manifest 恢复场景
    manifest = load_manifest(staging_dir)
    if manifest is None:
        raise ApiException(BusinessErrorCode.VIDEO_SCENE_CACHE_MISS)
    scenes = load_scenes(staging_dir)
    video_hash = manifest.get("video_hash", "")

    # 3. 检查已有描述（需与当前 scenes 对齐）
    if not force:
        cached_descriptions = _load_cached_descriptions(staging_dir)
        if cached_descriptions is not None and _descriptions_match_scenes(
            cached_descriptions, scenes
        ):
            return cached_descriptions

    # 4. 构造图片路径 & 并发描述
    grids_dir = get_grids_dir(staging_dir)

    if model_cfg is None:
        raise ApiException(BusinessErrorCode.COMMON_INVALID_ARGUMENT, "缺少大模型配置")

    llm_client = LLMClient(
        base_url=model_cfg.base_url,
        api_key=model_cfg.api_key,
        model_name=model_cfg.model_name,
        timeout=model_cfg.request_timeout or settings.llm_request_timeout,
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

    try:
        item_results: list[tuple[SceneDescriptionItem, WarningDTO | None]] = await gather(*tasks)
    finally:
        await llm_client.close()

    results = [item for item, _ in item_results]
    warnings: list[WarningDTO] = [w for _, w in item_results if w is not None]
    results.extend(skipped)
    elapsed = time.monotonic() - start

    # 按 scene_index 排序
    results.sort(key=lambda x: x.scene_index)

    result = SceneDescriptionResult(
        structure_job_id=structure_job_id,
        video_hash=video_hash,
        descriptions=results,
        warnings=warnings,
    )

    # 5. 保存描述
    _save_descriptions(staging_dir, result)

    logger.info(
        "场景描述完成: structure_job_id=%s, scenes=%d, elapsed=%.2fs",
        structure_job_id,
        len(results),
        elapsed,
    )
    return result
