from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from logging import getLogger

import numpy as np
from scenedetect import ContentDetector, FrameTimecode, SceneManager
from scenedetect.video_stream import VideoStream

from scene_detect.schemas.scene import SceneBoundary, SceneMetadata, ScenePolicyDTO, WarningDTO

logger = getLogger(__name__)


@dataclass(frozen=True)
class ScenePolicy:
    threshold: float
    min_scene_len_sec: float
    max_scene_count: int


SCENE_POLICY_TABLE: tuple[tuple[float, ScenePolicy], ...] = (
    (3 * 60, ScenePolicy(threshold=26.0, min_scene_len_sec=0.5, max_scene_count=30)),
    (10 * 60, ScenePolicy(threshold=27.0, min_scene_len_sec=0.8, max_scene_count=80)),
    (30 * 60, ScenePolicy(threshold=27.0, min_scene_len_sec=1.2, max_scene_count=150)),
    (90 * 60, ScenePolicy(threshold=28.0, min_scene_len_sec=1.8, max_scene_count=300)),
    (float("inf"), ScenePolicy(threshold=29.0, min_scene_len_sec=2.5, max_scene_count=500)),
)


def detect_scenes(
    video_path: str,
    threshold: float | None = None,
    max_scenes: int | None = None,
    *,
    scale_width: int | None = None,
    decode_threads: int | None = None,
) -> tuple[list[SceneBoundary], SceneMetadata, ScenePolicyDTO, list[WarningDTO]]:
    """用 PySceneDetect 检测场景边界（ffmpeg 管道解码）。

    默认策略遵循 docs/scene-detection-policy.md：
      - 按视频时长分档选择 threshold / min_scene_len_sec / max_scene_count
      - 仅执行一次正式检测
      - 检测后合并短场景
      - 如仍超上限，再按最短场景优先压缩到上限

    调用方若显式传入 ``threshold`` / ``max_scenes``，则优先使用显式值覆盖策略默认值。

    默认从 settings 读取管道参数：
      - ``video_detect_scale_width``（0=不缩放）
      - ``video_decode_threads``

    仅缩放、不降帧时，帧号/时间戳与原片对齐。
    """
    from scene_detect.core.settings import settings

    if scale_width is None:
        scale_width = settings.video_detect_scale_width
    if decode_threads is None:
        decode_threads = settings.video_decode_threads

    warnings: list[WarningDTO] = []

    # Step 1: 用 ffprobe 获取元信息（始终为原片）
    metadata = _extract_metadata(video_path)
    # Step 2: 按视频时长选择策略，并应用调用方显式覆盖项
    policy, effective_threshold, effective_max_scenes = _resolve_scene_settings(
        metadata.duration,
        threshold,
        max_scenes,
    )
    fps = metadata.fps
    total_frames = metadata.total_frames

    logger.info(
        "scene-detect 策略: video=%s duration=%.2fs threshold=%s min_scene_len=%.2fs max_scenes=%s",
        os.path.basename(video_path),
        metadata.duration,
        effective_threshold,
        policy.min_scene_len_sec,
        effective_max_scenes,
    )

    fs: FfmpegVideoStream | None = None
    try:
        # Step 3: 用 ffmpeg 管道 + PySceneDetect 做一次正式检测
        fs = FfmpegVideoStream(
            video_path,
            metadata.width,
            metadata.height,
            fps,
            total_frames,
            scale_width=scale_width,
            decode_threads=decode_threads,
        )
        logger.info(
            "scene-detect 管道: src=%dx%d scale=%s thr=%s detect=%dx%d",
            metadata.width,
            metadata.height,
            scale_width if scale_width > 0 else "off",
            decode_threads,
            *fs.frame_size,
        )

        scene_manager = SceneManager()
        scene_manager.auto_downscale = False
        scene_manager.downscale = 1
        scene_manager.add_detector(ContentDetector(threshold=effective_threshold))
        scene_manager.detect_scenes(video=fs)

        boundaries = [
            _boundary_from_range(idx, _tc_frame(start), _tc_frame(end), fps)
            for idx, (start, end) in enumerate(scene_manager.get_scene_list())
        ]
        if not boundaries:
            boundaries = [_full_video_boundary(total_frames, fps)]

        # Step 4: 合并短场景，再按最大场景数做兜底压缩
        final_boundaries = _post_process_scenes(boundaries, policy, effective_max_scenes, warnings)
        logger.info(
            "scene-detect 完成: video=%s raw_scenes=%d final_scenes=%d warnings=%d",
            os.path.basename(video_path),
            len(boundaries),
            len(final_boundaries),
            len(warnings),
        )
        return (
            final_boundaries,
            metadata,
            ScenePolicyDTO(
                threshold=effective_threshold,
                min_scene_len_sec=policy.min_scene_len_sec,
                max_scene_count=effective_max_scenes,
            ),
            warnings,
        )
    except Exception as exc:
        logger.warning("场景检测失败，回退为单场景: %s", exc)
        warnings.append(
            WarningDTO(
                code="scene_detect_fallback",
                message="场景检测失败，使用全视频作为单个场景",
                scope="scenes",
            )
        )
        return (
            [_full_video_boundary(total_frames, fps)],
            metadata,
            ScenePolicyDTO(
                threshold=effective_threshold,
                min_scene_len_sec=policy.min_scene_len_sec,
                max_scene_count=effective_max_scenes,
            ),
            warnings,
        )
    finally:
        if fs is not None:
            fs.close()


def select_scene_policy(duration_sec: float) -> ScenePolicy:
    """根据视频总时长，从策略表中选出一档场景策略。"""
    for max_duration_sec, policy in SCENE_POLICY_TABLE:
        if duration_sec < max_duration_sec:
            return policy
    return SCENE_POLICY_TABLE[-1][1]


def _resolve_scene_settings(
    duration_sec: float,
    threshold: float | None,
    max_scenes: int | None,
) -> tuple[ScenePolicy, float, int]:
    """合并时长策略与调用方显式覆盖值，得到最终检测参数。"""
    policy = select_scene_policy(duration_sec)
    effective_threshold = policy.threshold if threshold is None else threshold
    effective_max_scenes = policy.max_scene_count if max_scenes is None else max_scenes
    return policy, effective_threshold, effective_max_scenes


def _post_process_scenes(
    scenes: list[SceneBoundary],
    policy: ScenePolicy,
    max_scene_count: int,
    warnings: list[WarningDTO],
) -> list[SceneBoundary]:
    """按策略执行检测后处理，并把压缩信息写入 warnings。"""
    merged_scenes = merge_short_scenes(scenes, policy.min_scene_len_sec)
    if len(merged_scenes) < len(scenes):
        logger.warning(
            "scene-detect 短场景已合并: before=%d after=%d min_scene_len=%.2fs",
            len(scenes),
            len(merged_scenes),
            policy.min_scene_len_sec,
        )
        warnings.append(
            _build_scene_warning(
                "short_scenes_merged",
                (
                    f"短场景合并: {len(scenes)} -> {len(merged_scenes)} "
                    f"(min_scene_len_sec={policy.min_scene_len_sec})"
                ),
            )
        )

    final_scenes = shrink_to_max_scene_count(merged_scenes, max_scene_count)
    if (
        max_scene_count > 0
        and len(final_scenes) < len(merged_scenes)
        and len(merged_scenes) > max_scene_count
    ):
        logger.warning(
            "scene-detect 场景数已压缩: before=%d after=%d max_scene_count=%d",
            len(merged_scenes),
            len(final_scenes),
            max_scene_count,
        )
        warnings.append(
            _build_scene_warning(
                "scene_count_shrunk",
                (
                    f"场景数压缩: {len(merged_scenes)} -> {len(final_scenes)} "
                    f"(max_scene_count={max_scene_count})"
                ),
            )
        )

    return final_scenes


def _build_scene_warning(code: str, message: str) -> WarningDTO:
    """构造场景处理阶段的标准 warning。"""
    return WarningDTO(code=code, message=message, scope="scenes")


def merge_short_scenes(
    scenes: list[SceneBoundary],
    min_scene_len_sec: float,
) -> list[SceneBoundary]:
    """合并短场景：中间短场景并到后一个，末尾短场景并到前一个。"""
    if len(scenes) <= 1 or min_scene_len_sec <= 0:
        return _reindex_scenes(scenes)

    merged = list(scenes)
    index = 0
    while index < len(merged):
        if len(merged) == 1:
            break
        if _scene_duration_sec(merged[index]) >= min_scene_len_sec:
            index += 1
            continue

        if index < len(merged) - 1:
            merged[index + 1] = _merge_scene_pair(merged[index], merged[index + 1])
            del merged[index]
            continue

        merged[index - 1] = _merge_scene_pair(merged[index - 1], merged[index])
        del merged[index]
        index = max(0, index - 1)

    return _reindex_scenes(merged)


def shrink_to_max_scene_count(
    scenes: list[SceneBoundary],
    max_scene_count: int,
) -> list[SceneBoundary]:
    """若场景数超上限，持续合并当前最短场景直到满足上限。"""
    if max_scene_count <= 0 or len(scenes) <= max_scene_count:
        return _reindex_scenes(scenes)

    shrunk = list(scenes)
    while len(shrunk) > max_scene_count and len(shrunk) > 1:
        shortest_index = min(range(len(shrunk)), key=lambda idx: _scene_duration_sec(shrunk[idx]))
        if shortest_index < len(shrunk) - 1:
            shrunk[shortest_index + 1] = _merge_scene_pair(
                shrunk[shortest_index],
                shrunk[shortest_index + 1],
            )
            del shrunk[shortest_index]
            continue

        shrunk[shortest_index - 1] = _merge_scene_pair(
            shrunk[shortest_index - 1],
            shrunk[shortest_index],
        )
        del shrunk[shortest_index]

    return _reindex_scenes(shrunk)


def _scene_duration_sec(scene: SceneBoundary) -> float:
    """返回场景时长（秒）。"""
    return max(0.0, round(scene.end_time - scene.start_time, 6))


def _merge_scene_pair(left: SceneBoundary, right: SceneBoundary) -> SceneBoundary:
    """把两个相邻场景合并为一个连续场景。"""
    return SceneBoundary(
        scene_index=left.scene_index,
        start_frame=left.start_frame,
        end_frame=max(left.start_frame, right.end_frame),
        start_time=left.start_time,
        end_time=max(left.start_time, right.end_time),
    )


def _reindex_scenes(scenes: list[SceneBoundary]) -> list[SceneBoundary]:
    """重新生成连续的 scene_index，保持输出稳定。"""
    return [
        SceneBoundary(
            scene_index=idx,
            start_frame=scene.start_frame,
            end_frame=scene.end_frame,
            start_time=scene.start_time,
            end_time=scene.end_time,
        )
        for idx, scene in enumerate(scenes)
    ]


def _boundary_from_range(idx: int, start_tc: int, end_tc: int, fps: float) -> SceneBoundary:
    """PySceneDetect 的 end 为半开区间，转为闭区间帧边界。"""
    start_frame = max(0, start_tc)
    end_frame = max(start_frame, end_tc - 1)
    return SceneBoundary(
        scene_index=idx,
        start_frame=start_frame,
        end_frame=end_frame,
        start_time=_frame_to_time(start_frame, fps),
        end_time=_frame_to_time(end_frame + 1, fps),
    )


def _full_video_boundary(total_frames: int, fps: float) -> SceneBoundary:
    end_frame = max(0, total_frames - 1)
    return SceneBoundary(
        scene_index=0,
        start_frame=0,
        end_frame=end_frame,
        start_time=0.0,
        end_time=_frame_to_time(end_frame + 1, fps),
    )


def _tc_frame(tc: FrameTimecode) -> int:
    """兼容 scenedetect 0.7+ frame_num 与旧 get_frames()。"""
    if hasattr(tc, "frame_num"):
        return int(tc.frame_num)
    return int(tc.get_frames())


def _extract_metadata(video_path: str) -> SceneMetadata:
    from shared.core.ffprobe import query_video_metadata

    info = query_video_metadata(video_path)
    return SceneMetadata(
        fps=info["fps"],
        total_frames=info["total_frames"],
        duration=info["duration"],
        width=info["width"],
        height=info["height"],
    )


def _frame_to_time(frame: int, fps: float) -> float:
    if fps <= 0:
        return 0.0
    return round(frame / fps, 6)


def _scaled_size(width: int, height: int, scale_width: int) -> tuple[int, int]:
    """原片宽大于目标宽时按比例缩小；高度取偶以适配常见编码器约束。"""
    if scale_width <= 0 or width <= scale_width:
        return width, height
    scaled_h = max(2, int(round(height * scale_width / width)) // 2 * 2)
    return scale_width, scaled_h


class FfmpegVideoStream(VideoStream):
    """PySceneDetect 兼容的 VideoStream（ffmpeg 管道）。

    - ``scale_width > 0``: 管道内 scale，降低检测像素量
    - ``decode_threads``: ffmpeg ``-threads``（1 保守，2~4 更快，0=auto）
    """

    BACKEND_NAME = "ffmpeg_pipe"

    def __init__(
        self,
        video_path: str,
        width: int,
        height: int,
        fps: float,
        total_frames: int,
        *,
        scale_width: int = 0,
        decode_threads: int = 1,
    ):
        self._fps = fps
        self._total_frames = total_frames
        self._frame_number = 0
        self._width, self._height = _scaled_size(width, height, scale_width)
        if self._width <= 0 or self._height <= 0:
            raise ValueError(f"无效视频尺寸: {self._width}x{self._height}")
        self._frame_bytes = self._width * self._height * 3

        threads = int(decode_threads)
        if threads < 0:
            threads = 1

        cmd: list[str] = [
            shutil.which("ffmpeg") or "ffmpeg",
            "-nostdin",
            "-loglevel",
            "error",
            "-threads",
            str(threads),
            "-i",
            video_path,
            "-an",
        ]
        if (self._width, self._height) != (width, height):
            cmd += ["-vf", f"scale={self._width}:{self._height}"]
        cmd += ["-f", "rawvideo", "-pix_fmt", "bgr24", "-"]

        self._r_fd, w_fd = os.pipe()
        self._proc: subprocess.Popen | None = None
        try:
            self._proc = subprocess.Popen(  # noqa: S603 — video_path validated upstream
                cmd,
                stdout=w_fd,
                stderr=subprocess.DEVNULL,
                pass_fds=(w_fd,),
            )
        except Exception:
            os.close(w_fd)
            self.close()
            raise
        else:
            os.close(w_fd)

        fps_fraction = Fraction(self._fps).limit_denominator(1000000)
        self._timecode_base = FrameTimecode(timecode=0, fps=fps_fraction)
        self._duration: FrameTimecode | None = None
        if self._total_frames > 0:
            self._duration = self._timecode_base + self._total_frames
        self._name = os.path.basename(video_path)
        self._path = video_path

    @property
    def name(self) -> str:
        return self._name

    @property
    def path(self) -> str:
        return self._path

    @property
    def is_seekable(self) -> bool:
        return False

    @property
    def aspect_ratio(self) -> float:
        return 1.0

    def read(self, decode: bool = True):
        if self._r_fd < 0:
            return False
        raw = _read_exact(self._r_fd, self._frame_bytes)
        if not raw:
            self.close()
            return False
        self._frame_number += 1
        if decode:
            return np.frombuffer(raw, dtype=np.uint8).reshape((self._height, self._width, 3))
        return True

    @property
    def frame_size(self) -> tuple[int, int]:
        return (self._width, self._height)

    @property
    def position(self) -> FrameTimecode:
        if self._frame_number > 0:
            return self._timecode_base + (self._frame_number - 1)
        return self._timecode_base

    @property
    def frame_number(self) -> int:
        return self._frame_number

    @property
    def frame_rate(self) -> Fraction:
        return Fraction(self._fps).limit_denominator(1000000)

    @property
    def duration(self) -> FrameTimecode | None:
        return self._duration

    @property
    def base_timecode(self) -> FrameTimecode:
        return self._timecode_base

    @property
    def position_ms(self) -> float | None:
        return self._frame_number / self._fps * 1000 if self._fps > 0 else None

    def reset(self) -> None:
        self.close()

    def seek(self, target: float | str | FrameTimecode) -> None:  # type: ignore[override]
        raise NotImplementedError("FfmpegVideoStream does not support seeking")

    def close(self):
        if self._r_fd >= 0:
            with contextlib.suppress(OSError):
                os.close(self._r_fd)
            self._r_fd = -1
        if self._proc is None:
            return
        if self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
                self._proc.wait()
        else:
            self._proc.wait()
        self._proc = None


def _read_exact(fd: int, count: int) -> bytes | None:
    chunks: list[bytes] = []
    remaining = count
    while remaining > 0:
        try:
            chunk = os.read(fd, remaining)
        except OSError:
            return None
        if not chunk:
            return None
        chunks.append(chunk)
        remaining -= len(chunk)
    return b"".join(chunks)
