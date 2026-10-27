"""describe job 层错误契约测试：专用错误码 + 结构化 error_detail。

调用方（nowen-video）靠 error.code 判断"模型缺失"、靠 error.detail.model 定位具体模型，
不能再依赖正则解析 message，所以这些字段一旦回归就是线上链路断掉。
"""

from __future__ import annotations

import json

import pytest

from shared.jobs import build_job_status_response
from structure.services.llm.client import LLMRequestError
from structure.services.tasks import run_describe_scenes

_MODEL = "v-scheduler/minicpm-v4.6"


def _not_found_error() -> LLMRequestError:
    return LLMRequestError(
        f"全部 6 个场景描述失败（模型 {_MODEL}）：unknown model or upstream",
        model=_MODEL,
        base_url="http://v-scheduler:8080/v1",
        status_code=404,
        upstream_code="NOT_FOUND",
        upstream_message="unknown model or upstream",
        request_id="75cc452e-e385-49b4-bd2a-5c349c5c5820",
        failed_scenes=6,
        total_scenes=6,
    )


def _run(monkeypatch, exc: Exception) -> dict:
    """跑一次 describe 任务，返回最后一次 update_job 的 kwargs。"""
    calls: list[dict] = []

    async def _boom(**kwargs):
        raise exc

    monkeypatch.setattr(
        "structure.services.tasks.update_job", lambda job_id, **kw: calls.append(kw)
    )
    monkeypatch.setattr("structure.services.video.description.describe_scenes", _boom)

    with pytest.raises(type(exc)):
        run_describe_scenes.call_local("job1", "struct1")

    failed = [c for c in calls if c.get("status") == "failed"]
    assert len(failed) == 1
    return failed[0]


def test_missing_model_uses_dedicated_error_code(monkeypatch):
    """模型缺失 → DESCRIBE_MODEL_NOT_FOUND，detail 里带上完整 model id 与上游字段。"""
    payload = _run(monkeypatch, _not_found_error())

    assert payload["error_code"] == "DESCRIBE_MODEL_NOT_FOUND"
    assert payload["error_detail"]["model"] == _MODEL
    assert payload["error_detail"]["status_code"] == 404
    assert payload["error_detail"]["upstream_code"] == "NOT_FOUND"
    assert payload["error_detail"]["request_id"] == "75cc452e-e385-49b4-bd2a-5c349c5c5820"
    assert (payload["error_detail"]["failed_scenes"], payload["error_detail"]["total_scenes"]) == (
        6,
        6,
    )

    # message 只保留一层前缀，且不含整段 JSON
    assert payload["error_message"].count("大模型调用失败") == 1
    assert "{" not in payload["error_message"]


def test_missing_model_detected_without_matching_message_text(monkeypatch):
    """网关改了错误文案（不再含 unknown model）也必须给出专用码：判定只看结构。"""
    exc = LLMRequestError(
        f"全部 6 个场景描述失败（模型 {_MODEL}）：model not available",
        model=_MODEL,
        base_url="http://v-scheduler:8080/v1",
        status_code=404,
        upstream_code="NOT_FOUND",
        upstream_message="model not available",
    )
    payload = _run(monkeypatch, exc)

    assert payload["error_code"] == "DESCRIBE_MODEL_NOT_FOUND"


def test_not_found_from_other_cause_is_not_model_missing(monkeypatch):
    """404 但不是 NOT_FOUND 码（例如网关路由缺失）→ 仍走 DESCRIBE_ERROR。"""
    exc = LLMRequestError(
        f"全部 1 个场景描述失败（模型 {_MODEL}）：no route",
        model=_MODEL,
        status_code=404,
        upstream_code="NO_ROUTE",
    )
    payload = _run(monkeypatch, exc)

    assert payload["error_code"] == "DESCRIBE_ERROR"


def test_detail_base_url_has_no_credentials(monkeypatch):
    """调用方可在 model_cfg 里塞带密码的 base_url，detail 里不能原样落库。"""
    exc = LLMRequestError(
        f"全部 1 个场景描述失败（模型 {_MODEL}）：unauthorized",
        model=_MODEL,
        base_url="https://alice:s3cret@llm.example.com/v1",
        status_code=401,
        upstream_code="UNAUTHORIZED",
    )
    payload = _run(monkeypatch, exc)

    detail = payload["error_detail"]
    assert "s3cr3t" not in detail["base_url"]
    assert "alice" not in detail["base_url"]
    assert detail["base_url"] == "https://***@llm.example.com/v1"


def test_non_model_failure_keeps_describe_error(monkeypatch):
    """连接错误等非模型类失败 → 仍是 DESCRIBE_ERROR，但 detail.model 依旧存在。"""
    exc = LLMRequestError(
        f"全部 2 个场景描述失败（模型 {_MODEL}）：Connection error.",
        model=_MODEL,
        base_url="http://v-scheduler:8080/v1",
        failed_scenes=2,
        total_scenes=2,
    )
    payload = _run(monkeypatch, exc)

    assert payload["error_code"] == "DESCRIBE_ERROR"
    assert payload["error_detail"]["model"] == _MODEL
    assert "status_code" not in payload["error_detail"]


def _row(error_detail: str | None) -> dict:
    return {
        "job_id": "job1",
        "job_type": "describe",
        "status": "failed",
        "created_at": 1,
        "started_at": 2,
        "finished_at": 3,
        "attempt": 1,
        "progress": None,
        "result_json": None,
        "error_code": "DESCRIBE_ERROR",
        "error_message": "boom",
        "error_detail": error_detail,
    }


def test_status_response_parses_structured_detail():
    """结构化 error_detail 读出来是对象，调用方无需二次反序列化。"""
    detail = json.dumps({"model": _MODEL, "status_code": 404}, ensure_ascii=False)

    resp = build_job_status_response(_row(detail))

    assert resp.error is not None
    assert resp.error.detail == {"model": _MODEL, "status_code": 404}


def test_status_response_tolerates_legacy_text_detail():
    """历史记录里 error_detail 是纯文本：不得报错，原样返回。"""
    resp = build_job_status_response(_row("Connection error."))

    assert resp.error is not None
    assert resp.error.detail == "Connection error."


def test_status_response_tolerates_broken_json_detail():
    """以 { 开头但不是合法 JSON 的脏数据：退回原始字符串。"""
    resp = build_job_status_response(_row("{not json"))

    assert resp.error is not None
    assert resp.error.detail == "{not json"
