from __future__ import annotations

import json
import shutil
import subprocess
from fractions import Fraction


def extract_metadata(video_path: str) -> dict:
    """用 ffprobe 提取视频元数据，返回原始 dict。"""
    cmd = [
        shutil.which("ffprobe") or "ffprobe",
        "-v",
        "quiet",
        "-print_format",
        "json",
        "-show_format",
        "-show_streams",
        video_path,
    ]
    result = subprocess.run(  # noqa: S603 — video_path is an upload system path, validated upstream
        cmd, capture_output=True, text=True, check=False
    )
    if result.returncode != 0:
        raise RuntimeError(f"ffprobe 失败: {result.stderr.strip()}")

    probe = json.loads(result.stdout or "{}")
    video_stream = next(
        (s for s in probe.get("streams", []) if s.get("codec_type") == "video"),
        None,
    )
    if not video_stream:
        raise ValueError("未找到视频流")

    fmt = probe.get("format", {})

    def _parse_rate(rate: str | None) -> float:
        if not rate or rate == "0/0":
            return 0.0
        try:
            return float(Fraction(rate))
        except (ValueError, ZeroDivisionError):
            return 0.0

    fps = _parse_rate(video_stream.get("avg_frame_rate")) or _parse_rate(
        video_stream.get("r_frame_rate")
    )
    duration = float(video_stream.get("duration") or fmt.get("duration") or 0)
    total_frames = int(float(video_stream.get("nb_frames") or 0))
    if not total_frames and fps > 0 and duration > 0:
        total_frames = int(round(fps * duration))

    return {
        "video_path": video_path,
        "fps": fps,
        "duration": duration,
        "width": int(video_stream.get("width") or 0),
        "height": int(video_stream.get("height") or 0),
        "codec": video_stream.get("codec_name", ""),
        "bitrate": int(float(fmt.get("bit_rate") or video_stream.get("bit_rate") or 0)),
        "has_audio": any(s.get("codec_type") == "audio" for s in probe.get("streams", [])),
        "total_frames": total_frames,
    }
