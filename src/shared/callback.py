from __future__ import annotations

import asyncio
import json
import os
import time
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4

from pydantic import BaseModel

from shared.core.errors.error_codes import ErrorCode
from shared.core.errors.exceptions import ApiException


def assert_callback_url_available(callback_url: str) -> None:
    """Check that callback_url is reachable before accepting a task.

    A callback endpoint may reject HEAD/OPTIONS with 405 while still being usable for POST,
    so 405 is considered reachable. 404 and network failures are rejected.
    """
    for method in ("HEAD", "OPTIONS"):
        try:
            request = Request(callback_url, method=method)  # noqa: S310
            with urlopen(request, timeout=5) as response:  # noqa: S310
                if response.status < 500 and response.status != 404:
                    return
        except HTTPError as exc:
            if exc.code < 500 and exc.code not in {404}:
                return
        except URLError:
            continue
    raise ApiException(ErrorCode.EXTERNAL_SERVICE_ERROR, f"callback_url 不可用: {callback_url}")


async def send_multipart_event(
    callback_url: str,
    event: BaseModel | dict[str, Any],
    files: list[tuple[str, str, bytes, str]] | None = None,
    *,
    attempts: int | None = None,
    retry_delay_sec: float | None = None,
) -> None:
    body, content_type = encode_multipart(event, files or [])
    resolved_attempts = attempts if attempts is not None else _int_env("CALLBACK_RETRY_ATTEMPTS", 3)
    resolved_delay = (
        retry_delay_sec
        if retry_delay_sec is not None
        else float(os.getenv("CALLBACK_RETRY_DELAY_SEC", "1"))
    )
    await asyncio.to_thread(
        _post_multipart_with_retry,
        callback_url,
        body,
        content_type,
        max(resolved_attempts, 1),
        max(resolved_delay, 0),
    )


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def encode_multipart(
    event: BaseModel | dict[str, Any],
    files: list[tuple[str, str, bytes, str]],
) -> tuple[bytes, str]:
    boundary = f"video_instruction_{uuid4().hex}"
    chunks: list[bytes] = []

    def add(value: str | bytes) -> None:
        chunks.append(value.encode("utf-8") if isinstance(value, str) else value)

    event_payload = event.model_dump(mode="json") if isinstance(event, BaseModel) else event
    event_json = json.dumps(event_payload, ensure_ascii=False)
    add(f"--{boundary}\r\n")
    add('Content-Disposition: form-data; name="event"\r\n')
    add("Content-Type: application/json; charset=utf-8\r\n\r\n")
    add(event_json)
    add("\r\n")

    for field_name, filename, data, content_type in files:
        add(f"--{boundary}\r\n")
        add(
            f'Content-Disposition: form-data; name="{field_name}"; '
            f'filename="{filename}"\r\n'
        )
        add(f"Content-Type: {content_type}\r\n\r\n")
        add(data)
        add("\r\n")

    add(f"--{boundary}--\r\n")
    return b"".join(chunks), f"multipart/form-data; boundary={boundary}"


def _post_multipart(callback_url: str, body: bytes, content_type: str) -> None:
    request = Request(  # noqa: S310
        callback_url,
        data=body,
        headers={
            "Content-Type": content_type,
            "Content-Length": str(len(body)),
        },
        method="POST",
    )
    try:
        with urlopen(request, timeout=30) as response:  # noqa: S310
            if response.status >= 400:
                raise RuntimeError(f"callback failed with HTTP {response.status}")
    except URLError as exc:
        raise RuntimeError(f"callback request failed: {exc}") from exc


def _post_multipart_with_retry(
    callback_url: str,
    body: bytes,
    content_type: str,
    attempts: int,
    retry_delay_sec: float,
) -> None:
    last_exc: Exception | None = None
    for attempt in range(attempts):
        try:
            _post_multipart(callback_url, body, content_type)
            return
        except Exception as exc:
            last_exc = exc
            if attempt < attempts - 1:
                time.sleep(retry_delay_sec * (2**attempt))
    if last_exc is not None:
        raise last_exc
