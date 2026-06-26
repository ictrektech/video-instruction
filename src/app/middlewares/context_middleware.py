import re
import time
from uuid import uuid4

from fastapi import FastAPI, Request
from starlette.middleware.base import RequestResponseEndpoint
from starlette.responses import Response

from app.core.logging.access_log import log_access
from app.core.request_context import (
    clear_request_user,
    set_request_id,
)

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]{0,63}$")


def _new_request_id() -> str:
    return uuid4().hex[:12]


def _normalize_request_id(value: str | None) -> str:
    if not value:
        return _new_request_id()
    value = value.strip()
    if not value:
        return _new_request_id()
    if _REQUEST_ID_PATTERN.fullmatch(value):
        return value
    sanitized = re.sub(r"[^A-Za-z0-9_-]", "_", value)[:64].strip("_")
    return sanitized or _new_request_id()


def add_request_context_middleware(application: FastAPI) -> None:
    @application.middleware("http")
    async def request_context_middleware(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        start = time.perf_counter()
        request_id_value = _normalize_request_id(request.headers.get(REQUEST_ID_HEADER))
        set_request_id(request_id_value)
        response: Response | None = None
        try:
            response = await call_next(request)
            response.headers[REQUEST_ID_HEADER] = request_id_value
            return response
        finally:
            duration_ms = (time.perf_counter() - start) * 1000
            log_access(request=request, response=response, duration_ms=duration_ms)
            clear_request_user()
