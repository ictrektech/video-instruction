"""媒体源工具：统一处理本地路径与 HTTP(S) 视频流。

两个服务（scene-detect / structure）都需要在同一套逻辑下识别 URL、
透传路径、脱敏 URL、构造 ffmpeg/ffprobe 网络参数以及计算视频身份。
"""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from shared.utils.video_hash import compute_video_hash

HTTP_URL_PREFIXES = ("http://", "https://")

_TOKEN_QUERY_RE = re.compile(r"(token=)[^&\s]*")


def is_http_url(video_path: str) -> bool:
    """判断是否为 ``http://`` / ``https://`` URL。"""
    return video_path.startswith(HTTP_URL_PREFIXES)


def resolve_video_path(video_path: str, base_path: str) -> str:
    """解析媒体源到可处理路径。

    - HTTP(S) URL → 原样透传
    - 绝对路径（以 ``/`` 开头）→ 直接使用
    - 相对路径 → 拼接 ``base_path``（兼容旧模式）
    """
    if is_http_url(video_path):
        return video_path
    if video_path.startswith("/"):
        return video_path
    return str(Path(base_path) / video_path)


def redact_url(url: str) -> str:
    """脱敏 URL/文本中的 token query 参数，避免 token 进入日志。"""
    return _TOKEN_QUERY_RE.sub(r"\1***", url)


def ffmpeg_network_options() -> list[str]:
    """ffmpeg/ffprobe 读取 HTTP(S) 流时统一的网络参数。"""
    return [
        "-rw_timeout",
        "30000000",
        "-reconnect",
        "1",
        "-reconnect_streamed",
        "1",
        "-reconnect_delay_max",
        "5",
    ]


def video_identity(video_path: str) -> str:
    """计算视频身份。

    - 本地路径：继续使用采样 MD5（内容身份）
    - HTTP(S) URL：使用脱敏 URL 的 SHA-256（URL 身份，token 变化不影响）
    """
    if is_http_url(video_path):
        return hashlib.sha256(redact_url(video_path).encode("utf-8")).hexdigest()
    return compute_video_hash(video_path)
