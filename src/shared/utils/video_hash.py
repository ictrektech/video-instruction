"""视频内容哈希（采样 MD5），作为 jobs / 缓存的统一视频身份。"""

from __future__ import annotations

import hashlib
import os


def compute_video_hash(video_path: str) -> str:
    """极速采样哈希：3 点 × 16KB。

    适合边缘 NAS 等低性能设备。小文件（<1MB）直接算完整 MD5。

    Args:
        video_path: 视频文件路径。

    Returns:
        32 位十六进制 MD5 哈希值。
    """
    file_size = os.path.getsize(video_path)

    if file_size < 1024 * 1024:  # < 1MB
        with open(video_path, "rb") as f:
            return hashlib.md5(f.read()).hexdigest()  # noqa: S324

    md5 = hashlib.md5()  # noqa: S324
    md5.update(str(file_size).encode())

    positions = [
        0,
        file_size // 2,
        max(0, file_size - 16 * 1024),
    ]

    with open(video_path, "rb") as f:
        for pos in positions:
            f.seek(pos)
            md5.update(f.read(16 * 1024))

    return md5.hexdigest()
