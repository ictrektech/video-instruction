from __future__ import annotations

import json
import subprocess
from fractions import Fraction

from shared.utils.video_source import (
    ffmpeg_network_options,
    is_http_url,
    redact_url,
)


def _parse_rate(rate: str | None) -> float:
    """将 ffprobe 的帧率字符串（如 ``24000/1001``）解析为 float。"""
    if not rate or rate == "0/0":
        return 0.0
    try:
        return float(Fraction(rate))
    except (ValueError, ZeroDivisionError):
        return 0.0


def query_video_metadata(
    video_path: str,
    ffprobe_path: str = "ffprobe",
) -> dict:
    """用 ffprobe 提取视频元信息，返回解析后的 dict。

    Args:
        video_path: 视频文件绝对路径。
        ffprobe_path: ffprobe 可执行文件路径。

    Returns:
        dict，包含 fps / duration / width / height / total_frames / codec / bitrate / has_audio。

    Raises:
        RuntimeError: ffprobe 调用失败。
        ValueError: 未找到视频流。
    """
    cmd = [
        ffprobe_path,
        "-v",
        "error",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
    ]
    if is_http_url(video_path):
        cmd.extend(ffmpeg_network_options())
    cmd.append(video_path)

    result = subprocess.run(  # noqa: S603 — video_path validated upstream
        cmd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe 失败 (exit={result.returncode}): {redact_url(result.stderr.strip())}"
        )

    probe = json.loads(result.stdout or "{}")
    video_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        raise ValueError("未找到视频流")

    fmt = probe.get("format", {})

    fps = _parse_rate(video_stream.get("avg_frame_rate")) or _parse_rate(
        video_stream.get("r_frame_rate")
    )
    duration = float(video_stream.get("duration") or fmt.get("duration") or 0)
    total_frames_str = video_stream.get("nb_frames")
    if not total_frames_str:
        total_frames = int(round(fps * duration)) if fps > 0 and duration > 0 else 0
    else:
        total_frames = int(float(total_frames_str))

    return {
        "fps": fps,
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "total_frames": total_frames,
        "codec": video_stream.get("codec_name", ""),
        "bitrate": int(float(fmt.get("bit_rate") or video_stream.get("bit_rate") or 0)),
        "has_audio": any(s.get("codec_type") == "audio" for s in probe.get("streams", [])),
    }
