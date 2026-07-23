from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
from fractions import Fraction
from logging import getLogger

import numpy as np
from scenedetect import ContentDetector, SceneManager
from scenedetect.frame_timecode import FrameTimecode
from scenedetect.video_stream import VideoStream

from scene_detect.schemas.scene import SceneBoundary, SceneMetadata, WarningDTO

logger = getLogger(__name__)


def detect_scenes(
    video_path: str,
    threshold: float,
    max_scenes: int,
    *,
    scale_width: int | None = None,
    decode_threads: int | None = None,
) -> tuple[list[SceneBoundary], SceneMetadata, list[WarningDTO]]:
    """用 PySceneDetect 检测场景边界（ffmpeg 管道解码）。

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
    fps = metadata.fps
    total_frames = metadata.total_frames

    # Step 2: 场景检测
    fs: FfmpegVideoStream | None = None
    try:
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
        # 缩放已在 ffmpeg 完成，关闭库内二次 downscale
        scene_manager.auto_downscale = False
        scene_manager.downscale = 1
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video=fs)

        boundaries = [
            _boundary_from_range(idx, _tc_frame(start), _tc_frame(end), fps)
            for idx, (start, end) in enumerate(scene_manager.get_scene_list())
        ]
        if not boundaries:
            boundaries = [_full_video_boundary(total_frames, fps)]

        if max_scenes > 0 and len(boundaries) > max_scenes:
            warnings.append(
                WarningDTO(
                    code="scene_count_truncated",
                    message=f"场景数 {len(boundaries)} 截断至 {max_scenes}",
                    scope="scenes",
                )
            )
            boundaries = boundaries[:max_scenes]

        return boundaries, metadata, warnings
    except Exception as exc:
        logger.warning("场景检测失败，回退为单场景: %s", exc)
        warnings.append(
            WarningDTO(
                code="scene_detect_fallback",
                message="场景检测失败，使用全视频作为单个场景",
                scope="scenes",
            )
        )
        return [_full_video_boundary(total_frames, fps)], metadata, warnings
    finally:
        if fs is not None:
            fs.close()


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
