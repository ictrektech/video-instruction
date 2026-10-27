"""describe_scenes 失败语义测试：全部场景失败必须抛异常，而不是返回"成功"结果。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import openai
import pytest

from structure.schemas.description import SceneDescriptionResult
from structure.schemas.model_config import ModelConfig
from structure.schemas.video import SceneDTO
from structure.services.llm.client import LLMRequestError
from structure.services.video.cache import get_descriptions_path, get_staging_path
from structure.services.video.description import describe_scenes


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        staging_base_path=str(tmp_path / "staging"),
        llm_base_url="http://vrouter.test/v1",
        llm_api_key="",
        llm_model_name="vrouter-test-model",
        llm_max_concurrency=5,
        llm_request_timeout=5,
    )


def _scene_dto(index: int, grid_image: str | None) -> SceneDTO:
    return SceneDTO(
        scene_id=f"scene_{index}",
        scene_index=index,
        start_frame=0,
        end_frame=24,
        start_time=0.0,
        end_time=1.0,
        grid_image=grid_image,
    )


def _model_cfg() -> ModelConfig:
    return ModelConfig(base_url="http://llm.invalid/v1", model_name="test-model")


_COMPLETION = {
    "id": "chatcmpl-test",
    "object": "chat.completion",
    "created": 0,
    "model": "test-model",
    "choices": [
        {
            "index": 0,
            "message": {"role": "assistant", "content": "一张灰色图片。"},
            "finish_reason": "stop",
        }
    ],
}


class _FakeLLMClient:
    """可编程的 LLMClient �身：describe_image 按预设行为成功或抛错。"""

    def __init__(
        self,
        behavior: dict[int, bool],
        error: LLMRequestError | None = None,
        **kwargs,
    ) -> None:
        self.behavior = behavior
        self.error = error
        self.closed = False
        self.calls: list[int] = []
        self.kwargs = kwargs

    async def describe_image(self, image_path: Path, scene_index: int) -> str:
        self.calls.append(scene_index)
        if not self.behavior.get(scene_index, False):
            raise self.error or LLMRequestError("Connection error.")
        return f"描述 {scene_index}"

    async def close(self) -> None:
        self.closed = True


_CONNECTION_ERROR = LLMRequestError(
    "模型 v-scheduler/minicpm-v4.6 调用失败：Connection error.",
    model="v-scheduler/minicpm-v4.6",
    base_url="http://v-scheduler:8080/v1",
    reason="Connection error.",
)

_NOT_FOUND_ERROR = LLMRequestError(
    "模型 v-scheduler/minicpm-v4.6 调用失败（HTTP 404 NOT_FOUND）：unknown model or upstream",
    model="v-scheduler/minicpm-v4.6",
    base_url="http://v-scheduler:8080/v1",
    status_code=404,
    upstream_code="NOT_FOUND",
    upstream_message="unknown model or upstream",
    request_id="75cc452e-e385-49b4-bd2a-5c349c5c5820",
)


def _prepare(tmp_path: Path, monkeypatch, fake_client, scenes: list[SceneDTO]) -> Path:
    """准备 staging 目录并 patch 掉定位/加载与 LLMClient。"""
    staging_dir = get_staging_path("job123", _settings(tmp_path))
    grids = staging_dir / "grids"
    grids.mkdir(parents=True, exist_ok=True)
    for s in scenes:
        if s.grid_image is not None:
            (grids / s.grid_image).write_bytes(b"jpg")

    def _build_client(**kwargs) -> _FakeLLMClient:
        """记录构造参数后返回同一个假客户端，供断言实际生效的模型配置。"""
        fake_client.kwargs = kwargs
        return fake_client

    monkeypatch.setattr("structure.services.video.description.LLMClient", _build_client)
    monkeypatch.setattr(
        "structure.services.video.description._resolve_staging_dir",
        lambda job_id: staging_dir,
    )
    monkeypatch.setattr(
        "structure.services.video.description.load_manifest",
        lambda staging_dir: {"video_hash": "hash123"},
    )
    monkeypatch.setattr(
        "structure.services.video.description.load_scenes", lambda staging_dir: scenes
    )
    return staging_dir


@pytest.mark.asyncio
async def test_all_failed_raises_and_skips_cache(monkeypatch, tmp_path: Path):
    """全部场景描述失败 → 抛 LLMRequestError，且不落盘 descriptions.json。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    staging_dir = _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: False, 1: False}), scenes)

    with pytest.raises(LLMRequestError, match="全部 2 个场景描述失败"):
        await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    # 失败时不落盘，避免 force=False 重试命中失败缓存
    assert not get_descriptions_path(staging_dir).is_file()


@pytest.mark.asyncio
async def test_no_model_list_probe_before_describing(monkeypatch, tmp_path: Path):
    """不得在开跑前查 /models：网关的模型列表可能不完整，据此拦截会误杀可用配置。"""
    scenes = [_scene_dto(0, "scene_000.jpg")]
    staging_dir = get_staging_path("job123", _settings(tmp_path))
    (staging_dir / "grids").mkdir(parents=True, exist_ok=True)
    (staging_dir / "grids" / "scene_000.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(
        "structure.services.video.description._resolve_staging_dir", lambda job_id: staging_dir
    )
    monkeypatch.setattr(
        "structure.services.video.description.load_manifest",
        lambda staging_dir: {"video_hash": "hash123"},
    )
    monkeypatch.setattr(
        "structure.services.video.description.load_scenes", lambda staging_dir: scenes
    )

    paths: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        paths.append(request.url.path)
        return httpx.Response(200, json=_COMPLETION)

    real_client = openai.AsyncOpenAI

    def factory(**kwargs) -> openai.AsyncOpenAI:
        kwargs["http_client"] = httpx.AsyncClient(transport=httpx.MockTransport(handler))
        return real_client(**kwargs)

    monkeypatch.setattr("structure.services.llm.client.openai.AsyncOpenAI", factory)

    await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    assert [p for p in paths if p.endswith("/models")] == []
    assert [p for p in paths if p.endswith("/chat/completions")] == ["/v1/chat/completions"]


@pytest.mark.asyncio
async def test_all_failed_carries_structured_root_cause(monkeypatch, tmp_path: Path):
    """全失败时异常带根因（模型/上游），message 只有一层前缀且不含整段 JSON。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    _prepare(
        tmp_path,
        monkeypatch,
        _FakeLLMClient({0: False, 1: False}, error=_NOT_FOUND_ERROR),
        scenes,
    )

    with pytest.raises(LLMRequestError) as excinfo:
        await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    exc = excinfo.value
    assert exc.model == "v-scheduler/minicpm-v4.6"
    assert exc.upstream_code == "NOT_FOUND"
    assert exc.request_id == "75cc452e-e385-49b4-bd2a-5c349c5c5820"
    assert (exc.failed_scenes, exc.total_scenes) == (2, 2)
    # 只保留 error_code 前缀那一层，不再出现"大模型调用失败: 大模型调用失败:"
    assert str(exc).count("大模型调用失败") == 1
    assert "v-scheduler/minicpm-v4.6" in str(exc)
    assert "{" not in str(exc)

    detail = exc.to_detail()
    assert detail["model"] == "v-scheduler/minicpm-v4.6"
    assert detail["upstream_message"] == "unknown model or upstream"
    assert detail["failed_scenes"] == 2
    assert detail["total_scenes"] == 2


@pytest.mark.asyncio
async def test_all_failed_without_llm_error_still_names_model(monkeypatch, tmp_path: Path):
    """全失败但根因不是 LLM（如图片缺失）→ 仍要带上配置的模型名，不能给空串。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    staging_dir = _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: True, 1: True}), scenes)
    for s in scenes:
        (staging_dir / "grids" / s.grid_image).unlink()

    with pytest.raises(LLMRequestError) as excinfo:
        await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    exc = excinfo.value
    assert exc.to_detail()["model"] == "test-model"
    assert exc.upstream_code == ""
    assert exc.status_code is None
    # 消息里仍要说明真实原因，且只有一层前缀
    assert "图片文件不存在" in str(exc)
    assert str(exc).count("大模型调用失败") == 1


@pytest.mark.asyncio
async def test_connection_error_message_has_single_prefix(monkeypatch, tmp_path: Path):
    """连接类失败（无 upstream_message）→ 聚合消息不得叠加两层「大模型调用失败」。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    _prepare(
        tmp_path,
        monkeypatch,
        _FakeLLMClient({0: False, 1: False}, error=_CONNECTION_ERROR),
        scenes,
    )

    with pytest.raises(LLMRequestError) as excinfo:
        await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    exc = excinfo.value
    assert str(exc).count("大模型调用失败") == 1
    assert "Connection error." in str(exc)
    assert exc.model == "v-scheduler/minicpm-v4.6"
    assert exc.to_detail()["model"] == "v-scheduler/minicpm-v4.6"


@pytest.mark.asyncio
async def test_all_failed_missing_grids_reports_real_cause(monkeypatch, tmp_path: Path):
    """全部九宫格文件缺失 → 抛异常且消息带真实原因，而不是"未知错误"。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    staging_dir = _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: True, 1: True}), scenes)
    # 删除九宫格文件，模拟图片缺失
    for s in scenes:
        (staging_dir / "grids" / s.grid_image).unlink()

    with pytest.raises(LLMRequestError, match="图片文件不存在"):
        await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)


@pytest.mark.asyncio
async def test_partial_failure_returns_result_with_warnings(monkeypatch, tmp_path: Path):
    """部分场景失败 → 正常返回结果，失败场景带 DESC_LLM_ERROR warning。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    staging_dir = _prepare(
        tmp_path,
        monkeypatch,
        _FakeLLMClient({0: True, 1: False}, error=_NOT_FOUND_ERROR),
        scenes,
    )

    result = await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    assert isinstance(result, SceneDescriptionResult)
    statuses = {item.scene_index: item.status for item in result.descriptions}
    assert statuses == {0: "ok", 1: "failed"}
    assert [w.code for w in result.warnings] == ["DESC_LLM_ERROR"]
    assert result.status == "partial"
    # 逐场景排查：warning 里也要带同样的根因
    detail = result.warnings[0].detail
    assert detail["model"] == "v-scheduler/minicpm-v4.6"
    assert detail["upstream_code"] == "NOT_FOUND"
    assert detail["request_id"] == "75cc452e-e385-49b4-bd2a-5c349c5c5820"

    # 成功（含部分失败）时照常落盘
    saved = json.loads(get_descriptions_path(staging_dir).read_text(encoding="utf-8"))
    assert len(saved["descriptions"]) == 2
    assert len(saved["warnings"]) == 1


@pytest.mark.asyncio
async def test_partial_failure_retry_without_force_reuses_ok_items(monkeypatch, tmp_path: Path):
    """部分失败后 force=False 重试 → 复用成功项，仅重试 failed 场景。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    staging_dir = _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: True, 1: False}), scenes)
    await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    # 第二次：两个场景都能成功，但只有 scene 1 应该被重新调用
    second_client = _FakeLLMClient({0: True, 1: True})
    monkeypatch.setattr(
        "structure.services.video.description.LLMClient", lambda **kwargs: second_client
    )
    result = await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=False)

    assert second_client.calls == [1]
    statuses = {item.scene_index: item.status for item in result.descriptions}
    assert statuses == {0: "ok", 1: "ok"}
    assert result.warnings == []
    assert result.status == "completed"

    # 缓存更新为全部成功
    saved = json.loads(get_descriptions_path(staging_dir).read_text(encoding="utf-8"))
    assert all(item["status"] == "ok" for item in saved["descriptions"])
    assert saved["status"] == "completed"


@pytest.mark.asyncio
async def test_progress_cb_called_per_scene(monkeypatch, tmp_path: Path):
    """每完成一个场景调用一次 progress_cb (done, total)。"""
    scenes = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: True, 1: True}), scenes)

    calls: list[tuple[int, int]] = []
    await describe_scenes(
        "job123",
        _settings(tmp_path),
        _model_cfg(),
        force=True,
        progress_cb=lambda done, total: calls.append((done, total)),
    )

    assert calls == [(1, 2), (2, 2)]


@pytest.mark.asyncio
async def test_mismatched_cache_is_ignored(monkeypatch, tmp_path: Path):
    """缓存与当前 scenes 不对齐 → 完全忽略缓存全量重描述，不得复用旧场景的描述。"""
    scenes_a = [_scene_dto(0, "scene_000.jpg"), _scene_dto(1, "scene_001.jpg")]
    staging_dir = _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: True, 1: True}), scenes_a)
    await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    # scenes 变化（新增 scene 2），缓存 index 集合不再对齐
    scenes_b = scenes_a + [_scene_dto(2, "scene_002.jpg")]
    (staging_dir / "grids" / "scene_002.jpg").write_bytes(b"jpg")
    monkeypatch.setattr(
        "structure.services.video.description.load_scenes", lambda staging_dir: scenes_b
    )
    second_client = _FakeLLMClient({0: True, 1: True, 2: True})
    monkeypatch.setattr(
        "structure.services.video.description.LLMClient", lambda **kwargs: second_client
    )
    result = await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=False)

    # 全量重描述，而不是只补 scene 2
    assert second_client.calls == [0, 1, 2]
    assert {i.scene_index for i in result.descriptions} == {0, 1, 2}


@pytest.mark.asyncio
async def test_missing_model_cfg_falls_back_to_server_defaults(monkeypatch, tmp_path: Path):
    """不传 model_cfg → 用 settings 的服务端默认配置构造 LLMClient（默认即 V-Scheduler 免 key）。"""
    scenes = [_scene_dto(0, "scene_000.jpg")]
    client = _FakeLLMClient({0: True})
    _prepare(tmp_path, monkeypatch, client, scenes)

    result = await describe_scenes("job123", _settings(tmp_path), None, force=True)

    assert result.status == "completed"
    assert client.kwargs == {
        "base_url": "http://vrouter.test/v1",
        "api_key": "",
        "model_name": "vrouter-test-model",
        "timeout": 5,
    }


@pytest.mark.asyncio
async def test_explicit_model_cfg_overrides_server_defaults(monkeypatch, tmp_path: Path):
    """显式传入 model_cfg → 完全覆盖服务端默认配置。"""
    scenes = [_scene_dto(0, "scene_000.jpg")]
    client = _FakeLLMClient({0: True})
    _prepare(tmp_path, monkeypatch, client, scenes)

    await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    assert client.kwargs["base_url"] == "http://llm.invalid/v1"
    assert client.kwargs["model_name"] == "test-model"


@pytest.mark.asyncio
async def test_partial_model_cfg_merges_with_server_defaults(monkeypatch, tmp_path: Path):
    """只传部分字段（如仅 max_concurrency）→ 其余字段回落服务端默认。"""
    scenes = [_scene_dto(0, "scene_000.jpg")]
    client = _FakeLLMClient({0: True})
    _prepare(tmp_path, monkeypatch, client, scenes)

    result = await describe_scenes(
        "job123", _settings(tmp_path), ModelConfig(max_concurrency=10), force=True
    )

    assert result.status == "completed"
    assert client.kwargs == {
        "base_url": "http://vrouter.test/v1",
        "api_key": "",
        "model_name": "vrouter-test-model",
        "timeout": 5,
    }
