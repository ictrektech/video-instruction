from __future__ import annotations

import pytest

from shared import callback


@pytest.mark.asyncio
async def test_send_multipart_event_retries_until_success(monkeypatch):
    attempts: list[int] = []

    def flaky_post(_url: str, _body: bytes, _content_type: str) -> None:
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("temporary failure")

    monkeypatch.setattr(callback, "_post_multipart", flaky_post)

    await callback.send_multipart_event(
        "http://callback.local",
        {"status": "succeeded"},
        attempts=3,
        retry_delay_sec=0,
    )

    assert len(attempts) == 3
