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
) -> tuple[list[SceneBoundary], SceneMetadata, list[WarningDTO]]:
    """用 PySceneDetect 检测场景边界（单线程 ffmpeg 管道解码）。

    Args:
        video_path: 视频文件绝对路径。
        threshold: 场景检测阈值（越大越不敏感）。
        max_scenes: 最大场景数限制，0 表示不限制。

    Returns:
        (boundaries, metadata, warnings)
    """
    warnings: list[WarningDTO] = []

    # Step 1: 用 ffprobe 获取元信息
    metadata = _extract_metadata(video_path)
    fps = metadata.fps
    total_frames = metadata.total_frames
    width = metadata.width
    height = metadata.height

    # Step 2: 场景检测
    fs: FfmpegVideoStream | None = None
    try:
        fs = FfmpegVideoStream(video_path, width, height, fps, total_frames)
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=threshold))
        scene_manager.detect_scenes(video=fs)
        scene_list = scene_manager.get_scene_list()

        boundaries: list[SceneBoundary] = []
        for idx, (start, end) in enumerate(scene_list):
            start_frame = max(0, start.get_frames())
            end_frame = max(start_frame, end.get_frames() - 1)
            boundaries.append(
                SceneBoundary(
                    scene_index=idx,
                    start_frame=start_frame,
                    end_frame=end_frame,
                    start_time=_frame_to_time(start_frame, fps),
                    end_time=_frame_to_time(end_frame + 1, fps),
                )
            )

        if not boundaries:
            end_frame = max(0, total_frames - 1)
            boundaries.append(
                SceneBoundary(
                    scene_index=0,
                    start_frame=0,
                    end_frame=end_frame,
                    start_time=0.0,
                    end_time=_frame_to_time(end_frame + 1, fps),
                )
            )

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
        end_frame = max(0, total_frames - 1)
        return (
            [
                SceneBoundary(
                    scene_index=0,
                    start_frame=0,
                    end_frame=end_frame,
                    start_time=0.0,
                    end_time=_frame_to_time(end_frame + 1, fps),
                )
            ],
            metadata,
            warnings,
        )
    finally:
        if fs is not None:
            fs.close()


def _extract_metadata(video_path: str) -> SceneMetadata:
    """用 ffprobe 提取视频元信息。"""
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


class FfmpegVideoStream(VideoStream):
    """PySceneDetect 兼容的 VideoStream，基于单线程 ffmpeg 管道。

    使用 ``-threads 1`` 限制 h264 解码器为单线程，避免 OpenCV 后端
    无节制占用 CPU（700%+ 峰值）。
    """

    BACKEND_NAME = "ffmpeg_pipe"

    def __init__(
        self,
        video_path: str,
        width: int,
        height: int,
        fps: float,
        total_frames: int,
    ):
        self._width = width
        self._height = height
        self._fps = fps
        self._total_frames = total_frames
        self._frame_number = 0

        if self._width <= 0 or self._height <= 0:
            raise ValueError(f"无效视频尺寸: {self._width}x{self._height}")
        self._frame_bytes = self._width * self._height * 3

        self._r_fd, w_fd = os.pipe()
        self._proc: subprocess.Popen | None = None
        try:
            self._proc = subprocess.Popen(  # noqa: S603 — video_path validated upstream from upload system
                [
                    shutil.which("ffmpeg") or "ffmpeg",
                    "-nostdin",
                    "-loglevel",
                    "error",
                    "-threads",
                    "1",
                    "-i",
                    video_path,
                    "-an",
                    "-f",
                    "rawvideo",
                    "-pix_fmt",
                    "bgr24",
                    "-",
                ],
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
