"""describe_scenes 失败语义测试：全部场景失败必须抛异常，而不是返回"成功"结果。"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

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


class _FakeLLMClient:
    """可编程的 LLMClient �身：describe_image 按预设行为成功或抛错。"""

    def __init__(self, behavior: dict[int, bool], **kwargs) -> None:
        self.behavior = behavior
        self.closed = False
        self.calls: list[int] = []
        self.kwargs = kwargs

    async def describe_image(self, image_path: Path, scene_index: int) -> str:
        self.calls.append(scene_index)
        if not self.behavior.get(scene_index, False):
            raise LLMRequestError("Connection error.")
        return f"描述 {scene_index}"

    async def close(self) -> None:
        self.closed = True


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
    staging_dir = _prepare(tmp_path, monkeypatch, _FakeLLMClient({0: True, 1: False}), scenes)

    result = await describe_scenes("job123", _settings(tmp_path), _model_cfg(), force=True)

    assert isinstance(result, SceneDescriptionResult)
    statuses = {item.scene_index: item.status for item in result.descriptions}
    assert statuses == {0: "ok", 1: "failed"}
    assert [w.code for w in result.warnings] == ["DESC_LLM_ERROR"]
    assert result.status == "partial"

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
    """不传 model_cfg → 用 settings 的服务端默认配置构造 LLMClient（默认即 V-Router 免 key）。"""
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
