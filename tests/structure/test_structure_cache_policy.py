"""structure 缓存命中与 force/miss 清理策略测试。"""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from structure.schemas.description import SceneDescriptionItem, SceneDescriptionResult
from structure.schemas.video import (
    SceneBoundaryInput,
    SceneDTO,
    StructureCommand,
    StructureResultDTO,
    VideoMetadataSchema,
)
from structure.services.video.cache import invalidate_cache_dir, scenes_match
from structure.services.video.description import _descriptions_match_scenes
from structure.services.video.pipeline import structure


def _boundary(
    index: int,
    start_frame: int,
    end_frame: int,
    start_time: float,
    end_time: float,
) -> SceneBoundaryInput:
    return SceneBoundaryInput(
        scene_index=index,
        start_frame=start_frame,
        end_frame=end_frame,
        start_time=start_time,
        end_time=end_time,
    )


def _scene_dto(
    index: int,
    start_frame: int,
    end_frame: int,
    start_time: float,
    end_time: float,
    grid_image: str | None = None,
) -> SceneDTO:
    return SceneDTO(
        scene_id=f"scene_{index}",
        scene_index=index,
        start_frame=start_frame,
        end_frame=end_frame,
        start_time=start_time,
        end_time=end_time,
        grid_image=grid_image,
    )


def _metadata(duration: float = 1.0, total_frames: int = 25) -> dict:
    return {
        "fps": 25.0,
        "duration": duration,
        "width": 1280,
        "height": 720,
        "codec": "h264",
        "bitrate": 1000,
        "has_audio": False,
        "total_frames": total_frames,
    }


def _patch_structure_env(
    monkeypatch,
    tmp_path: Path,
    *,
    cached_result: StructureResultDTO | None,
    video_hash: str = "hash123",
):
    """准备 structure 测试环境：真实 cache_dir，mock 掉 hash/metadata/昂贵 IO。"""
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"fake-video")
    cache_dir = tmp_path / "cache" / "scenes" / video_hash
    cache_dir.mkdir(parents=True, exist_ok=True)

    settings_stub = SimpleNamespace(
        video_work_dir=str(tmp_path / "work"),
        cache_base_path=str(tmp_path / "cache"),
        video_scenes_dir="scenes",
        video_grid_tile_max_height=180,
    )
    monkeypatch.setattr("structure.services.video.pipeline.settings", settings_stub)
    monkeypatch.setattr(
        "structure.services.video.pipeline.compute_video_hash",
        lambda _path: video_hash,
    )
    monkeypatch.setattr(
        "structure.services.video.pipeline.get_cache_path",
        lambda _hash, _settings: cache_dir,
    )
    monkeypatch.setattr(
        "structure.services.video.pipeline.load_cached_result",
        lambda _cache_dir, _base: cached_result,
    )
    monkeypatch.setattr(
        "structure.services.video.pipeline.extract_metadata",
        lambda _path: _metadata(),
    )
    return video, cache_dir


class TestScenesMatch:
    def test_match_same_bounds_across_input_and_dto(self):
        request = [_boundary(0, 0, 24, 0.0, 1.0), _boundary(1, 25, 49, 1.0, 2.0)]
        cached = [
            _scene_dto(0, 0, 24, 0.0, 1.0, "scene_001.jpg"),
            _scene_dto(1, 25, 49, 1.0, 2.0, "scene_002.jpg"),
        ]
        assert scenes_match(request, cached)

    def test_mismatch_when_bounds_differ(self):
        request = [_boundary(0, 0, 24, 0.0, 1.0)]
        cached = [_scene_dto(0, 0, 49, 0.0, 2.0)]
        assert not scenes_match(request, cached)

    def test_mismatch_when_count_differs(self):
        request = [_boundary(0, 0, 24, 0.0, 1.0), _boundary(1, 25, 49, 1.0, 2.0)]
        cached = [_scene_dto(0, 0, 24, 0.0, 1.0)]
        assert not scenes_match(request, cached)


class TestInvalidateCacheDir:
    def test_removes_structure_grids_and_descriptions(self, tmp_path: Path):
        cache_dir = tmp_path / "scenes" / "abc"
        grids = cache_dir / "grids"
        grids.mkdir(parents=True)
        (grids / "scene_001.jpg").write_bytes(b"old")
        (grids / "scene_099.jpg").write_bytes(b"stale")
        (cache_dir / "_cached.json").write_text("{}", encoding="utf-8")
        (cache_dir / "_descriptions.json").write_text("{}", encoding="utf-8")

        invalidate_cache_dir(cache_dir)

        assert not cache_dir.exists()

    def test_noop_when_missing(self, tmp_path: Path):
        missing = tmp_path / "missing"
        invalidate_cache_dir(missing)
        assert not missing.exists()


class TestDescriptionsMatchScenes:
    def test_match_same_indexes(self):
        descriptions = SceneDescriptionResult(
            video_hash="h",
            descriptions=[
                SceneDescriptionItem(scene_index=0, grid_image="a.jpg", status="ok"),
                SceneDescriptionItem(scene_index=1, grid_image="b.jpg", status="ok"),
            ],
        )
        scenes = [_scene_dto(0, 0, 1, 0.0, 0.1), _scene_dto(1, 2, 3, 0.1, 0.2)]
        assert _descriptions_match_scenes(descriptions, scenes)

    def test_mismatch_count(self):
        descriptions = SceneDescriptionResult(
            video_hash="h",
            descriptions=[
                SceneDescriptionItem(scene_index=0, grid_image="a.jpg", status="ok"),
                SceneDescriptionItem(scene_index=1, grid_image="b.jpg", status="ok"),
            ],
        )
        scenes = [_scene_dto(0, 0, 1, 0.0, 0.1)]
        assert not _descriptions_match_scenes(descriptions, scenes)


class TestStructureCachePolicy:
    @pytest.mark.asyncio
    async def test_cache_hit_when_scenes_match(self, monkeypatch, tmp_path: Path):
        cached_result = StructureResultDTO(
            video_hash="hash123",
            metadata=VideoMetadataSchema(video_path="demo.mp4"),
            grid_base_path="scenes/hash123/grids/",
            scenes=[_scene_dto(0, 0, 24, 0.0, 1.0, "scene_001.jpg")],
            stage_timings={"total": 1.0},
            elapsed_sec=1.0,
        )
        video, cache_dir = _patch_structure_env(monkeypatch, tmp_path, cached_result=cached_result)
        (cache_dir / "grids").mkdir(exist_ok=True)
        (cache_dir / "grids" / "scene_001.jpg").write_bytes(b"grid")

        extract = Mock(side_effect=AssertionError("should hit cache"))
        monkeypatch.setattr("structure.services.video.pipeline.extract_metadata", extract)

        result = await structure(
            StructureCommand(
                video_path="demo.mp4",
                scenes=[_boundary(0, 0, 24, 0.0, 1.0)],
                force=False,
                frame_grid=False,
            ),
            str(video),
        )
        assert result.scenes[0].end_frame == 24
        extract.assert_not_called()
        assert cache_dir.exists()

    @pytest.mark.asyncio
    async def test_scenes_mismatch_invalidates_and_recomputes(self, monkeypatch, tmp_path: Path):
        cached_result = StructureResultDTO(
            video_hash="hash123",
            metadata=VideoMetadataSchema(video_path="demo.mp4"),
            grid_base_path="scenes/hash123/grids/",
            scenes=[_scene_dto(0, 0, 24, 0.0, 1.0, "scene_001.jpg")],
        )
        video, cache_dir = _patch_structure_env(monkeypatch, tmp_path, cached_result=cached_result)
        (cache_dir / "grids").mkdir(exist_ok=True)
        (cache_dir / "grids" / "scene_001.jpg").write_bytes(b"old")
        (cache_dir / "grids" / "scene_099.jpg").write_bytes(b"stale")
        (cache_dir / "_descriptions.json").write_text("{}", encoding="utf-8")
        (cache_dir / "_cached.json").write_text("{}", encoding="utf-8")

        # 使用真实 invalidate，验证脏文件被清掉
        saved = Mock()
        monkeypatch.setattr(
            "structure.services.video.pipeline.save_cached_result",
            saved,
        )
        monkeypatch.setattr(
            "structure.services.video.pipeline.extract_metadata",
            lambda _path: _metadata(duration=2.0, total_frames=50),
        )

        result = await structure(
            StructureCommand(
                video_path="demo.mp4",
                scenes=[
                    _boundary(0, 0, 24, 0.0, 1.0),
                    _boundary(1, 25, 49, 1.0, 2.0),
                ],
                force=False,
                frame_grid=False,
            ),
            str(video),
        )

        assert len(result.scenes) == 2
        saved.assert_called_once()
        # invalidate 会删掉旧目录；save mock 不重建，所以目录应不存在
        assert not cache_dir.exists()

    @pytest.mark.asyncio
    async def test_force_invalidates_even_when_scenes_match(self, monkeypatch, tmp_path: Path):
        cached_result = StructureResultDTO(
            video_hash="hash123",
            metadata=VideoMetadataSchema(video_path="demo.mp4"),
            grid_base_path="scenes/hash123/grids/",
            scenes=[_scene_dto(0, 0, 24, 0.0, 1.0, "scene_001.jpg")],
        )
        video, cache_dir = _patch_structure_env(monkeypatch, tmp_path, cached_result=cached_result)
        (cache_dir / "_cached.json").write_text("{}", encoding="utf-8")
        (cache_dir / "_descriptions.json").write_text("{}", encoding="utf-8")
        (cache_dir / "grids").mkdir(exist_ok=True)
        (cache_dir / "grids" / "scene_001.jpg").write_bytes(b"old")

        saved = Mock()
        monkeypatch.setattr("structure.services.video.pipeline.save_cached_result", saved)

        result = await structure(
            StructureCommand(
                video_path="demo.mp4",
                scenes=[_boundary(0, 0, 24, 0.0, 1.0)],
                force=True,
                frame_grid=False,
            ),
            str(video),
        )
        assert len(result.scenes) == 1
        saved.assert_called_once()
        assert not cache_dir.exists()

    @pytest.mark.asyncio
    async def test_cache_disabled_skips_read_invalidate_and_save(
        self, monkeypatch, tmp_path: Path
    ):
        cached_result = StructureResultDTO(
            video_hash="hash123",
            metadata=VideoMetadataSchema(video_path="demo.mp4"),
            grid_base_path="scenes/hash123/grids/",
            scenes=[_scene_dto(0, 0, 24, 0.0, 1.0, "scene_001.jpg")],
        )
        video, cache_dir = _patch_structure_env(monkeypatch, tmp_path, cached_result=cached_result)
        (cache_dir / "_cached.json").write_text("{}", encoding="utf-8")

        load = Mock(side_effect=AssertionError("cache disabled should not read"))
        invalidate = Mock(side_effect=AssertionError("cache disabled should not invalidate"))
        save = Mock(side_effect=AssertionError("cache disabled should not write"))
        monkeypatch.setattr("structure.services.video.pipeline.load_cached_result", load)
        monkeypatch.setattr("structure.services.video.pipeline.invalidate_cache_dir", invalidate)
        monkeypatch.setattr("structure.services.video.pipeline.save_cached_result", save)

        result = await structure(
            StructureCommand(
                video_path="demo.mp4",
                scenes=[_boundary(0, 0, 24, 0.0, 1.0)],
                cache_enabled=False,
                frame_grid=False,
            ),
            str(video),
        )

        assert len(result.scenes) == 1
        assert result.grid_base_path == ""
        assert cache_dir.exists()
        load.assert_not_called()
        invalidate.assert_not_called()
        save.assert_not_called()
