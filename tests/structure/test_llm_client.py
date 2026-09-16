"""LLMClient 行为测试：免验证鉴权、token 预算与空响应处理。

这两类行为都容易静默回归：openai>=2.44 在构造期强制要求凭据、在请求期又要求
Authorization 头「存在或显式省略」；而推理型模型的 reasoning_content 计入 max_tokens，
预算过小会让 content 变成空串。
"""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

import httpx
import openai
import pytest

from structure.services.llm.client import LLMClient, LLMRequestError

_CONTENT = "一张灰色图片。"
_COMPLETION: dict[str, Any] = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": _CONTENT},
            "finish_reason": "stop",
        }
    ],
}


async def _call(
    monkeypatch, tmp_path: Path, api_key: str, completion: dict[str, Any]
) -> tuple[httpx.Request, Any]:
    """用 MockTransport 替换底层 HTTP，返回 (实际发出的请求, 返回值或异常)。"""
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=completion)

    real_client = openai.AsyncOpenAI

    def factory(**kwargs) -> openai.AsyncOpenAI:
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr("structure.services.llm.client.openai.AsyncOpenAI", factory)

    image = tmp_path / "grid.jpg"
    image.write_bytes(b"\xff\xd8\xff")
    client = LLMClient(base_url="http://v-router:8080/v1", api_key=api_key, model_name="test-model")
    try:
        outcome: Any = await client.describe_image(image, 0)
    except Exception as exc:  # noqa: BLE001 - 测试需要把异常当结果返回
        outcome = exc
    finally:
        await client.close()
    return seen[0], outcome


@pytest.mark.asyncio
async def test_empty_api_key_sends_no_authorization_header(monkeypatch, tmp_path: Path):
    """免验证模式：空 api_key 必须能构造成功，且请求不带 Authorization 头。"""
    request, text = await _call(monkeypatch, tmp_path, "", _COMPLETION)

    assert "authorization" not in request.headers
    assert text == _CONTENT


@pytest.mark.asyncio
async def test_real_api_key_still_sends_authorization_header(monkeypatch, tmp_path: Path):
    """带 key 的 provider 行为不变，仍正常发送 Authorization 头。"""
    request, _ = await _call(monkeypatch, tmp_path, "sk-real", _COMPLETION)

    assert request.headers["authorization"] == "Bearer sk-real"


@pytest.mark.asyncio
async def test_token_budget_covers_reasoning_overhead(monkeypatch, tmp_path: Path):
    """max_tokens 必须留足推理预算，否则推理模型会返回空 content。"""
    request, _ = await _call(monkeypatch, tmp_path, "", _COMPLETION)

    assert json.loads(request.content)["max_tokens"] >= 512


@pytest.mark.asyncio
async def test_empty_content_is_treated_as_failure(monkeypatch, tmp_path: Path):
    """空 content 不得当作成功，否则会静默写入空描述。"""
    empty = copy.deepcopy(_COMPLETION)
    empty["choices"][0]["message"]["content"] = ""

    _, outcome = await _call(monkeypatch, tmp_path, "", empty)

    assert isinstance(outcome, LLMRequestError)
    assert "为空" in str(outcome)
