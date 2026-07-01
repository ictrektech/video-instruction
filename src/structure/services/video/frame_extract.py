from __future__ import annotations

import shutil
import subprocess
import tempfile
import uuid
from logging import getLogger
from pathlib import Path

from PIL import Image, ImageFile

from structure.schemas.video import SceneDTO, WarningDTO

ImageFile.LOAD_TRUNCATED_IMAGES = True

logger = getLogger(__name__)


def extract_scene_grids(
    video_path: str,
    scene_bounds: list[tuple[int, int, float, float]],
    metadata: dict,
    work_dir: Path,
    tile_max_height: int,
    cache_dir: Path | None = None,
) -> list[tuple[SceneDTO, list[WarningDTO]]]:
    """为每个场景采样 9 帧并拼接为 3x3 九宫格。

    scene_bounds 为 (start_frame, end_frame, start_time, end_time) 四元组。
    """
    grids_dir = work_dir / "grids"
    grids_dir.mkdir(parents=True, exist_ok=True)

    results: list[tuple[SceneDTO, list[WarningDTO]]] = []

    for index, (start_frame, end_frame, start_time, end_time) in enumerate(scene_bounds):
        scene_id = f"scene_{uuid.uuid4().hex[:8]}"
        scene_warnings: list[WarningDTO] = []

        try:
            frame_indices = _sample_frames(
                start_frame, end_frame, 9, start_ratio=0.05, end_ratio=0.95
            )

            grid_path = grids_dir / f"{scene_id}.jpg"
            fps = metadata.get("fps", 25.0)
            _build_grid(
                video_path,
                frame_indices,
                fps,
                grid_path,
                tile_max_height,
            )

            # 若指定了缓存目录，将 grid 图片持久化到缓存路径
            if cache_dir is not None:
                cache_grid_dir = cache_dir / "grids"
                cache_grid_dir.mkdir(parents=True, exist_ok=True)
                persistent_path = cache_grid_dir / f"scene_{index + 1:03d}.jpg"
                shutil.copy2(grid_path, persistent_path)
                grid_image = f"scene_{index + 1:03d}.jpg"
            else:
                grid_image = None

            dto = SceneDTO(
                scene_id=scene_id,
                scene_index=index,
                start_time=start_time,
                end_time=end_time,
                start_frame=start_frame,
                end_frame=end_frame,
                grid_image=grid_image,
            )
            results.append((dto, scene_warnings))
        except Exception as exc:
            logger.warning("场景 %d 九宫格生成失败: %s", index + 1, exc)
            scene_warnings.append(
                WarningDTO(
                    code="grid_failed",
                    message=f"场景 {index + 1} 九宫格生成失败: {exc}",
                    scope="frame_grid",
                    target_id=f"scene_index:{index}",
                )
            )
            dto = SceneDTO(
                scene_id=scene_id,
                scene_index=index,
                start_time=start_time,
                end_time=end_time,
                start_frame=start_frame,
                end_frame=end_frame,
            )
            results.append((dto, scene_warnings))

    return results


def scene_bounds_to_dtos(
    scene_bounds: list[tuple[int, int, float, float]],
) -> list[SceneDTO]:
    """将场景边界转换为不含网格图的 DTO 列表。

    scene_bounds 为 (start_frame, end_frame, start_time, end_time) 四元组。
    """
    dtos: list[SceneDTO] = []
    for index, (start_frame, end_frame, start_time, end_time) in enumerate(scene_bounds):
        dtos.append(
            SceneDTO(
                scene_id=f"scene_{uuid.uuid4().hex[:8]}",
                scene_index=index,
                start_time=start_time,
                end_time=end_time,
                start_frame=start_frame,
                end_frame=end_frame,
            )
        )
    return dtos


def _sample_frames(
    start_frame: int,
    end_frame: int,
    count: int,
    start_ratio: float,
    end_ratio: float,
) -> list[int]:
    """在 [start_frame, end_frame] 区间内均匀采样 count 帧。"""
    full_span = end_frame - start_frame
    if full_span <= 0:
        return [start_frame] * count
    s = int(round(start_frame + full_span * start_ratio))
    e = int(round(start_frame + full_span * end_ratio))
    span = e - s
    if span <= 0:
        return [s] * count
    if count == 1:
        return [s + span // 2]
    return [int(round(s + span * i / (count - 1))) for i in range(count)]


def _build_grid(
    video_path: str,
    frame_indices: list[int],
    fps: float,
    out_path: Path,
    tile_max_height: int,
) -> None:
    """用 ffmpeg 取帧，PIL 拼成 3x3 九宫格保存为 JPEG。"""
    if not frame_indices:
        blank = Image.new("RGB", (960, 720), (0, 0, 0))
        blank.save(out_path, "JPEG", quality=85)
        return

    with tempfile.TemporaryDirectory(prefix="grid_") as tmp:
        tmp_dir = Path(tmp)
        frame_paths = _extract_frames(video_path, frame_indices, tmp_dir, "f", fps)

        if not frame_paths:
            blank = Image.new("RGB", (960, 720), (0, 0, 0))
            blank.save(out_path, "JPEG", quality=85)
            return

        while len(frame_paths) < 9:
            dup = tmp_dir / f"f_{len(frame_paths) + 1:02d}.jpg"
            shutil.copy2(frame_paths[-1], dup)
            frame_paths.append(dup)

        images = []
        for fp in frame_paths[:9]:
            with Image.open(fp) as img:
                images.append(img.convert("RGB"))

        tile_w, tile_h = _grid_tile_size(images, tile_max_height)
        canvas = Image.new("RGB", (tile_w * 3, tile_h * 3))
        for idx, img in enumerate(images):
            resized = img.resize((tile_w, tile_h), Image.Resampling.BILINEAR)
            row, col = divmod(idx, 3)
            canvas.paste(resized, (col * tile_w, row * tile_h))
        canvas.save(out_path, "JPEG", quality=85)


def _grid_tile_size(images: list[Image.Image], max_h: int = 360) -> tuple[int, int]:
    first = images[0]
    if first.height > max_h:
        ratio = max_h / first.height
        return max(1, int(round(first.width * ratio))), max_h
    return max(1, first.width), max(1, first.height)


def _extract_frames(
    video_path: str,
    frame_numbers: list[int],
    out_dir: Path,
    prefix: str,
    fps_val: float,
) -> list[Path]:
    """用 ffmpeg 快速 seek + 时间范围截取提取指定帧。

    利用 ``-ss`` 提前 seek + ``-to`` 限定时长，避免全解码。
    通过 ``fps`` 过滤器在场景时间范围内均匀输出帧，每场景仅一次 ffmpeg 调用。

    Args:
        video_path: 视频文件路径。
        frame_numbers: 要提取的帧号列表（决定时间范围）。
        out_dir: 输出目录。
        prefix: 输出文件前缀。
        fps_val: 视频帧率，用于将帧号转为时间点。

    Returns:
        按 ``frame_numbers`` 顺序排列的输出路径列表。
    """
    if not frame_numbers:
        return []

    out_dir.mkdir(parents=True, exist_ok=True)

    # 取最小/最大帧号作为时间范围（留 2% 边距避免端点帧丢失）
    first_fn = max(0, min(frame_numbers))
    last_fn = max(frame_numbers)
    start_time = first_fn / fps_val
    end_time = last_fn / fps_val
    duration = max(0.1, end_time - start_time)

    count = len(frame_numbers)
    target_fps = count / duration

    output_pattern = out_dir / f"{prefix}_%03d.jpg"

    subprocess.run(  # noqa: S603
        [
            shutil.which("ffmpeg") or "ffmpeg",
            "-y",
            "-hide_banner",
            "-loglevel",
            "error",
            "-ss",
            f"{start_time:.3f}",
            "-i",
            video_path,
            "-to",
            f"{end_time:.3f}",
            "-vf",
            f"fps={target_fps:.6f}",
            "-frames:v",
            str(count),
            "-q:v",
            "5",
            "-an",
            str(output_pattern),
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    extracted = sorted(out_dir.glob(f"{prefix}_*.jpg"))
    # fps 过滤器输出已按时间均匀分布，直接补齐到 count 个
    while len(extracted) < count:
        extracted.append(extracted[-1] if extracted else Path())
    # 防止超出 count（ffmpeg 可能多输出 1 帧）
    return extracted[:count]
