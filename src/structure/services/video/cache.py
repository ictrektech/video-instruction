from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
from logging import getLogger
from pathlib import Path

from structure.core.settings import Settings
from structure.schemas.video import SceneDTO, StructureResultDTO, VideoMetadataSchema, WarningDTO

logger = getLogger(__name__)


def compute_video_hash(video_path: str) -> str:
    """
    极速采样哈希：3点×16KB
    适合边缘 NAS、树莓派等低性能设备
    Args:
        video_path: 视频文件路径
    Returns:
        32位十六进制 MD5 哈希值
    """
    file_size = os.path.getsize(video_path)

    # 小文件直接计算完整哈希
    if file_size < 1024 * 1024:  # < 1MB
        return hashlib.md5(open(video_path, "rb").read()).hexdigest()  # noqa: S324

    # 初始化 MD5
    md5 = hashlib.md5()  # noqa: S324

    # 加入文件大小作为种子（增加区分度）
    md5.update(str(file_size).encode())

    # 采样位置：开头、中间、结尾
    positions = [
        0,  # 开头
        file_size // 2,  # 中间
        max(0, file_size - 16 * 1024),  # 结尾（避免越界）
    ]

    with open(video_path, "rb") as f:
        for pos in positions:
            # 定位到采样点
            f.seek(pos)
            # 读取 16KB
            data = f.read(16 * 1024)
            md5.update(data)

    return md5.hexdigest()


def _scenes_cache_root(settings: Settings) -> Path:
    """返回 scenes 缓存的根目录。"""
    return Path(settings.cache_base_path) / settings.video_scenes_dir


def get_cache_path(video_hash: str, settings: Settings) -> Path:
    """返回 `<cache_base_path>/scenes/<hash>/` 目录。"""
    return _scenes_cache_root(settings) / video_hash


def _grids_dir(cache_dir: Path) -> Path:
    return cache_dir / "grids"


def _cached_json_path(cache_dir: Path) -> Path:
    return cache_dir / "_cached.json"


# ── 缓存序列化 ──────────────────────────────────────────────────────────


class _CachedData:
    """`_cached.json` 的序列化结构。"""

    def __init__(
        self,
        cache_version: int,
        video_hash: str,
        grid_base_path: str,
        metadata: VideoMetadataSchema,
        scenes: list[dict],
        warnings: list[dict],
        stage_timings: dict[str, float],
        elapsed_sec: float,
    ):
        self.cache_version = cache_version
        self.video_hash = video_hash
        self.grid_base_path = grid_base_path
        self.metadata = metadata
        self.scenes = scenes
        self.warnings = warnings
        self.stage_timings = stage_timings
        self.elapsed_sec = elapsed_sec

    def to_dict(self) -> dict:
        return {
            "cache_version": self.cache_version,
            "video_hash": self.video_hash,
            "grid_base_path": self.grid_base_path,
            "metadata": self.metadata.model_dump(),
            "scenes": self.scenes,
            "warnings": self.warnings,
            "stage_timings": self.stage_timings,
            "elapsed_sec": self.elapsed_sec,
        }

    @classmethod
    def from_dict(cls, data: dict) -> _CachedData:
        return cls(
            cache_version=data["cache_version"],
            video_hash=data["video_hash"],
            grid_base_path=data.get("grid_base_path", ""),
            metadata=VideoMetadataSchema(**data["metadata"]),
            scenes=data["scenes"],
            warnings=data["warnings"],
            stage_timings=data.get("stage_timings", {}),
            elapsed_sec=data.get("elapsed_sec", 0.0),
        )


_CURRENT_CACHE_VERSION = 2


def _scene_to_cached_dict(scene: SceneDTO) -> dict:
    return {
        "scene_id": scene.scene_id,
        "scene_index": scene.scene_index,
        "start_time": scene.start_time,
        "end_time": scene.end_time,
        "start_frame": scene.start_frame,
        "end_frame": scene.end_frame,
        "grid_image": scene.grid_image,
    }


def _scene_from_cached_dict(data: dict) -> SceneDTO:
    return SceneDTO(
        scene_id=data["scene_id"],
        scene_index=data.get("scene_index", 0),
        start_time=data["start_time"],
        end_time=data["end_time"],
        start_frame=data["start_frame"],
        end_frame=data["end_frame"],
        grid_image=data.get("grid_image"),
    )


# ── 读写缓存 ──────────────────────────────────────────────────────────


def load_cached_result(
    cache_dir: Path,
    cache_base_path: str | Path | None = None,
) -> StructureResultDTO | None:
    """从缓存目录加载完整结果。"""
    json_path = _cached_json_path(cache_dir)
    if not json_path.is_file():
        return None

    try:
        with open(json_path, encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("缓存元数据损坏，重新处理: %s", exc)
        return None

    try:
        cached = _CachedData.from_dict(raw)
    except (KeyError, TypeError) as exc:
        logger.warning("缓存元数据格式异常，重新处理: %s", exc)
        return None

    if cached.cache_version != _CURRENT_CACHE_VERSION:
        logger.warning(
            "缓存版本不匹配 (%s != %s)，重新处理", cached.cache_version, _CURRENT_CACHE_VERSION
        )
        return None

    scenes: list[SceneDTO] = []
    for scene_data in cached.scenes:
        grid_image = scene_data.get("grid_image")
        if grid_image and cache_base_path:
            grid_abs = Path(cache_base_path) / cached.grid_base_path / grid_image
            if not grid_abs.is_file():
                logger.warning(
                    "场景 %d 的 grid 图片缺失，缓存失效", scene_data.get("scene_index", 0)
                )
                return None

        scenes.append(_scene_from_cached_dict(scene_data))

    warnings = [WarningDTO(**w) for w in cached.warnings]

    return StructureResultDTO(
        video_hash=cached.video_hash,
        metadata=cached.metadata,
        grid_base_path=cached.grid_base_path,
        scenes=scenes,
        warnings=warnings,
        stage_timings=cached.stage_timings,
        elapsed_sec=cached.elapsed_sec,
    )


def save_cached_result(
    cache_dir: Path,
    result: StructureResultDTO,
) -> None:
    """保存结构化结果到缓存。"""
    grids_path = _grids_dir(cache_dir)
    grids_path.mkdir(parents=True, exist_ok=True)

    cached_data = _CachedData(
        cache_version=_CURRENT_CACHE_VERSION,
        video_hash=result.video_hash,
        grid_base_path=result.grid_base_path,
        metadata=result.metadata,
        scenes=[_scene_to_cached_dict(s) for s in result.scenes],
        warnings=[w.model_dump() for w in result.warnings],
        stage_timings=result.stage_timings,
        elapsed_sec=result.elapsed_sec,
    )

    json_path = _cached_json_path(cache_dir)
    fd, tmp_path = tempfile.mkstemp(dir=cache_dir, suffix=".tmp")
    try:
        with open(fd, "w", encoding="utf-8") as f:
            json.dump(cached_data.to_dict(), f, ensure_ascii=False, indent=2)
        shutil.move(tmp_path, json_path)
    except Exception:
        Path(tmp_path).unlink(missing_ok=True)
        raise

    logger.info("缓存已保存: %s", cache_dir)


def clear_cache(video_hash: str, settings: Settings) -> None:
    """删除指定视频的缓存目录。"""
    cache_dir = get_cache_path(video_hash, settings)
    if cache_dir.is_dir():
        shutil.rmtree(cache_dir)
        logger.info("缓存已清除: %s", cache_dir)
