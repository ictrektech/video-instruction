"""scene-detect 服务通用工具函数。"""

from __future__ import annotations


def coalesce[T](value: T | None, default: T) -> T:
    """``None`` 时回退到 default，保留 0/False 等合法值。"""
    return default if value is None else value
