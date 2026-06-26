from __future__ import annotations

from shared.core.ffprobe import query_video_metadata


def extract_metadata(video_path: str) -> dict:
    """用 ffprobe 提取视频元数据，返回原始 dict。"""
    info = query_video_metadata(video_path)
    info["video_path"] = video_path
    return info
