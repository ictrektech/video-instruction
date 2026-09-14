from __future__ import annotations

from http import HTTPStatus
from logging import getLogger

from fastapi import Request
from starlette.responses import Response

_access_logger = getLogger("shared.access")


def log_access(request: Request, response: Response | None, duration_ms: float) -> None:
    """记录访问日志。

    Args:
        request (Request): FastAPI 请求对象。
        response (Response | None): 响应对象，可能为 None（例如内部错误）。
        duration_ms (float): 处理请求所用时间，单位为毫秒。
    """
    status_code = response.status_code if response else 500
    try:
        status_phrase = HTTPStatus(status_code).phrase
    except ValueError:
        status_phrase = "-"

    client_addr = f"{request.client.host}:{request.client.port}" if request.client else "-"
    query = f"?{request.url.query}" if request.url.query else ""

    _access_logger.info(
        f"{request.url.path}{query}",
        extra={
            "client_addr": client_addr,
            "method": request.method,
            "status_code": status_code,
            "status_phrase": status_phrase,
            "duration_ms": duration_ms,
        },
    )
