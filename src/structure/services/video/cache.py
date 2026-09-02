"""结构化产物暂存（staging）管理。

structure 服务无状态：每个 job 的产物写进独立 staging 目录
``<staging_base>/<structure_job_id>/``，上游轮询到 job succeeded 后把整个目录
``mv`` 到自己的数据目录。服务端不维护跨请求持久缓存、不管理资产状态。
"""

from __future__ import annotations

import json
import shutil
import tempfile
import time
import uuid
from logging import getLogger
from pathlib import Path
from typing import Any

from structure.core.settings import Settings
from structure.schemas.video import (
    SceneDTO,
    StructureResultDTO,
    VideoMetadataSchema,
    WarningDTO,
)

logger = getLogger(__name__)

# manifest 文件名（产物目录内）
MANIFEST_FILENAME = "manifest.json"
METADATA_FILENAME = "metadata.json"
GRIDS_DIRNAME = "grids"
DESCRIPTIONS_FILENAME = "descriptions.json"


def get_staging_path(job_id: str, settings: Settings) -> Path:
    """返回 ``<staging_base>/<job_id>/`` 目录。"""
    return Path(settings.staging_base_path) / job_id


def get_manifest_path(staging_dir: Path) -> Path:
    return staging_dir / MANIFEST_FILENAME


def get_grids_dir(staging_dir: Path) -> Path:
    return staging_dir / GRIDS_DIRNAME


def get_descriptions_path(staging_dir: Path) -> Path:
    return staging_dir / DESCRIPTIONS_FILENAME


def staging_dir_from_row(row: dict) -> Path | None:
    """从 structure job 的 result_ref 解析 staging 目录（不存在返回 None）。"""
    ref = row.get("result_ref")
    if not ref:
        return None
    try:
        data = json.loads(ref)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(data, dict):
        return None
    value = data.get("staging_dir")
    return Path(value) if value else None


# ── manifest 构建 ──────────────────────────────────────────────────────────


def build_manifest(result: StructureResultDTO) -> dict[str, Any]:
    """将结构化结果序列化为 ``manifest.json`` 内容。

    manifest 记录视频身份（hash）、场景边界与九宫格、各阶段耗时，供上游归档审计。
    仅作元数据，不参与命名或去重。
    """
    return {
        "version": 1,
        "video_hash": result.video_hash,
        "metadata": result.metadata.model_dump(),
        "scenes": [
            {
                "scene_id": s.scene_id,
                "scene_index": s.scene_index,
                "start_time": s.start_time,
                "end_time": s.end_time,
                "start_frame": s.start_frame,
                "end_frame": s.end_frame,
                "grid_image": s.grid_image,
            }
            for s in result.scenes
        ],
        "warnings": [w.model_dump() for w in result.warnings],
        "stage_timings": result.stage_timings,
        "elapsed_sec": result.elapsed_sec,
        "created_at": int(time.time()),
    }


# ── 写入 staging ──────────────────────────────────────────────────────────


def write_staging(
    staging_dir: Path,
    result: StructureResultDTO,
    *,
    grids_dir_src: Path | None = None,
) -> None:
    """将结构化结果写入 staging 目录。

    - 若 ``grids_dir_src`` 提供（grid 图片暂存于工作目录），将其移入 staging/grids。
    - 写入 ``manifest.json``（原子写，先临时文件再 rename）。
    - ``metadata.json`` 与 manifest 内容冗余，但便于上游直接读取，仍保留。

    成功后 staging 目录即为上游可整体 ``mv`` 的完整产物。
    """
    staging_dir.mkdir(parents=True, exist_ok=True)

    # 1. grids：从工作目录移入（若本 job 生成过）
    if grids_dir_src is not None and grids_dir_src.is_dir():
        grids_dst = get_grids_dir(staging_dir)
        grids_dst.mkdir(parents=True, exist_ok=True)
        for grid_file in sorted(grids_dir_src.iterdir()):
            if grid_file.is_file():
                shutil.move(str(grid_file), str(grids_dst / grid_file.name))

    # 2. metadata.json
    _atomic_write_json(staging_dir / METADATA_FILENAME, result.metadata.model_dump())

    # 3. manifest.json（最后写，作为产物完整性的标志）
    _atomic_write_json(get_manifest_path(staging_dir), build_manifest(result))

    logger.info("staging 已写入: %s", staging_dir)


def _atomic_write_json(path: Path, data: dict[str, Any]) -> None:
    """原子写 JSON：先写临时文件再 rename，避免读到半成品。"""
    fd, tmp_path = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise


# ── 读取 staging（供 describe 复用同一产物目录）─────────────────────────


def load_manifest(staging_dir: Path) -> dict[str, Any] | None:
    """读取 staging 目录的 manifest.json。"""
    path = get_manifest_path(staging_dir)
    if not path.is_file():
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("manifest 读取失败: %s (%s)", path, exc)
        return None


def load_scenes(staging_dir: Path) -> list[SceneDTO]:
    """从 manifest 恢复场景列表（供 describe 读取 grids）。"""
    manifest = load_manifest(staging_dir)
    if manifest is None:
        return []
    scenes: list[SceneDTO] = []
    for scene_data in manifest.get("scenes", []):
        scenes.append(
            SceneDTO(
                scene_id=scene_data["scene_id"],
                scene_index=scene_data.get("scene_index", 0),
                start_time=scene_data["start_time"],
                end_time=scene_data["end_time"],
                start_frame=scene_data["start_frame"],
                end_frame=scene_data["end_frame"],
                grid_image=scene_data.get("grid_image"),
            )
        )
    return scenes


def load_metadata(staging_dir: Path) -> VideoMetadataSchema | None:
    """从 manifest 恢复视频元数据。"""
    manifest = load_manifest(staging_dir)
    if manifest is None or not manifest.get("metadata"):
        return None
    return VideoMetadataSchema(**manifest["metadata"])


def load_warnings(staging_dir: Path) -> list[WarningDTO]:
    """从 manifest 恢复警告列表。"""
    manifest = load_manifest(staging_dir)
    if manifest is None:
        return []
    return [WarningDTO(**w) for w in manifest.get("warnings", [])]


# ── TTL 清理（卫生，非缓存）───────────────────────────────────────────────


def cleanup_expired_staging(
    settings: Settings,
    now: int | None = None,
) -> int:
    """清理超过 ``staging_ttl_sec`` 未被搬走的 staging 目录。

    上游没搬 = 任务失败 / 被丢弃，产物不再被认领。只删无人认领的过期目录，
    不碰正在被上游 ``mv`` 的目录（rename 原子，删除器和搬移器不冲突）。
    """
    ttl = settings.staging_ttl_sec
    if ttl <= 0:
        return 0

    root = Path(settings.staging_base_path)
    if not root.is_dir():
        return 0

    now = now if now is not None else int(time.time())
    deadline = now - ttl
    removed = 0

    for entry in root.iterdir():
        if not entry.is_dir():
            continue
        # 只清理 job_id 形态的目录，避免误删 staging 根目录下的非 job 目录
        try:
            uuid.UUID(entry.name)
        except ValueError:
            continue
        try:
            if entry.stat().st_mtime < deadline:
                shutil.rmtree(entry)
                removed += 1
                logger.info("staging TTL 清理: %s", entry)
        except OSError as exc:
            logger.warning("staging 清理失败 %s: %s", entry, exc)

    return removed
