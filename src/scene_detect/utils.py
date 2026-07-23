"""scene-detect 服务通用工具函数。"""

from __future__ import annotations

from pathlib import Path
from typing import TypeVar

T = TypeVar("T")


def resolve_video_path(video_path: str, base_path: str) -> str:
    """解析视频路径到容器内可访问的绝对路径。

    - 绝对路径（以 ``/`` 开头）→ 直接使用（宿主机路径 = 容器内路径，由 volume 映射保证）
    - 相对路径 → 拼接 ``base_path``（兼容旧模式，如 immich 路径）
    """
    if video_path.startswith("/"):
        return video_path
    return str(Path(base_path) / video_path)


def coalesce(value: T | None, default: T) -> T:
    """``None`` 时回退到 default，保留 0/False 等合法值。"""
    return default if value is None else value
