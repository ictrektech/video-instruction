"""structure 无状态化：staging 产物写入与 TTL 清理测试。"""

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
    WarningDTO,
)
from structure.services.video.cache import (
    cleanup_expired_staging,
    get_staging_path,
    load_manifest,
    load_scenes,
    load_warnings,
    write_staging,
)
from structure.services.video.description import _descriptions_match_scenes
from structure.services.video.pipeline import structure


def _settings(tmp_path: Path) -> SimpleNamespace:
    return SimpleNamespace(
        video_work_dir=str(tmp_path / "work"),
        staging_base_path=str(tmp_path / "staging"),
        staging_ttl_sec=3600,
        video_grid_tile_max_height=180,
        video_grid_ffmpeg_threads=0,
    )


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


def _result(video_hash: str = "hash123", grid_image: str = "scene_001.jpg") -> StructureResultDTO:
    return StructureResultDTO(
        video_hash=video_hash,
        metadata=VideoMetadataSchema(video_path="demo.mp4"),
        staging_dir="/staging/job123",
        scenes=[
            _scene_dto(0, 0, 24, 0.0, 1.0, grid_image),
            _scene_dto(1, 25, 49, 1.0, 2.0, None),
        ],
        warnings=[WarningDTO(code="w1", message="warning", scope="s", target_id="t")],
        stage_timings={"total": 1.0},
        elapsed_sec=1.0,
    )


class TestGetStagingPath:
    def test_names_by_job_id(self, tmp_path: Path):
        settings = _settings(tmp_path)
        path = get_staging_path("job123", settings)
        assert path == Path(tmp_path) / "staging" / "job123"


class TestWriteStaging:
    def test_writes_manifest_metadata_and_grids(self, tmp_path: Path):
        settings = _settings(tmp_path)
        staging_dir = get_staging_path("job123", settings)
        result = _result()

        # 模拟 frame_extract 已把 grid 写进 staging/grids/
        grids = staging_dir / "grids"
        grids.mkdir(parents=True)
        (grids / "scene_001.jpg").write_bytes(b"grid-jpg")

        write_staging(staging_dir, result, grids_dir_src=None)

        assert (staging_dir / "manifest.json").is_file()
        assert (staging_dir / "metadata.json").is_file()
        assert (grids / "scene_001.jpg").is_file()

        manifest = load_manifest(staging_dir)
        assert manifest is not None
        assert manifest["video_hash"] == "hash123"
        assert len(manifest["scenes"]) == 2
        assert manifest["scenes"][0]["grid_image"] == "scene_001.jpg"
        assert manifest["scenes"][1]["grid_image"] is None
        assert len(manifest["warnings"]) == 1

    def test_load_scenes_restores_dtos(self, tmp_path: Path):
        settings = _settings(tmp_path)
        staging_dir = get_staging_path("job123", settings)
        write_staging(staging_dir, _result())

        scenes = load_scenes(staging_dir)
        assert len(scenes) == 2
        assert scenes[0].end_frame == 24
        assert scenes[0].grid_image == "scene_001.jpg"

    def test_load_warnings(self, tmp_path: Path):
        settings = _settings(tmp_path)
        staging_dir = get_staging_path("job123", settings)
        write_staging(staging_dir, _result())

        warnings = load_warnings(staging_dir)
        assert len(warnings) == 1
        assert warnings[0].code == "w1"


class TestCleanupExpiredStaging:
    def test_removes_expired_dirs(self, tmp_path: Path):
        settings = _settings(tmp_path)
        root = Path(settings.staging_base_path)
        old = root / "11111111-1111-1111-1111-111111111111"
        new = root / "22222222-2222-2222-2222-222222222222"
        old.mkdir(parents=True)
        new.mkdir(parents=True)

        # 伪造 mtime：old 目录 TTL 之外，new 目录 TTL 之内
        old_mtime = 1_000_000_000
        old.stat  # ensure exists
        import os

        os.utime(old, (old_mtime, old_mtime))

        now = old_mtime + 7200  # 超过 ttl=3600
        removed = cleanup_expired_staging(settings, now=now)

        assert removed == 1
        assert not old.exists()
        assert new.exists()

    def test_skips_non_job_dirs(self, tmp_path: Path):
        settings = _settings(tmp_path)
        root = Path(settings.staging_base_path)
        legacy = root / "scenes"
        legacy.mkdir(parents=True)
        import os

        os.utime(legacy, (1_000_000_000, 1_000_000_000))
        removed = cleanup_expired_staging(settings, now=1_000_000_000 + 7200)
        assert removed == 0
        assert legacy.exists()

    def test_noop_when_ttl_zero(self, tmp_path: Path):
        settings = _settings(tmp_path)
        settings.staging_ttl_sec = 0
        old = Path(settings.staging_base_path) / "old_job"
        old.mkdir(parents=True)
        removed = cleanup_expired_staging(settings)
        assert removed == 0
        assert old.exists()


class TestDescriptionsMatchScenes:
    def test_match_same_indexes(self):
        descriptions = SceneDescriptionResult(
            structure_job_id="j",
            descriptions=[
                SceneDescriptionItem(scene_index=0, grid_image="a.jpg", status="ok"),
                SceneDescriptionItem(scene_index=1, grid_image="b.jpg", status="ok"),
            ],
        )
        scenes = [_scene_dto(0, 0, 1, 0.0, 0.1), _scene_dto(1, 2, 3, 0.1, 0.2)]
        assert _descriptions_match_scenes(descriptions, scenes)

    def test_mismatch_count(self):
        descriptions = SceneDescriptionResult(
            structure_job_id="j",
            descriptions=[
                SceneDescriptionItem(scene_index=0, grid_image="a.jpg", status="ok"),
                SceneDescriptionItem(scene_index=1, grid_image="b.jpg", status="ok"),
            ],
        )
        scenes = [_scene_dto(0, 0, 1, 0.0, 0.1)]
        assert not _descriptions_match_scenes(descriptions, scenes)


class TestStructurePipeline:
    @pytest.mark.asyncio
    async def test_writes_staging_and_returns_staging_dir(self, monkeypatch, tmp_path: Path):
        video = tmp_path / "demo.mp4"
        video.write_bytes(b"fake-video")
        settings = _settings(tmp_path)
        staging_dir = get_staging_path("job123", settings)

        monkeypatch.setattr("structure.services.video.pipeline.settings", settings)
        monkeypatch.setattr(
            "structure.services.video.pipeline.compute_video_hash",
            lambda _path: "hash123",
        )
        monkeypatch.setattr(
            "structure.services.video.pipeline.extract_metadata",
            lambda _path: _metadata(),
        )

        extract = Mock(
            return_value=[
                (_scene_dto(0, 0, 24, 0.0, 1.0, "scene_001.jpg"), []),
                (_scene_dto(1, 25, 49, 1.0, 2.0, "scene_002.jpg"), []),
            ]
        )
        monkeypatch.setattr(
            "structure.services.video.pipeline.extract_scene_grids",
            extract,
        )

        result = await structure(
            StructureCommand(
                video_path="demo.mp4",
                scenes=[_boundary(0, 0, 24, 0.0, 1.0), _boundary(1, 25, 49, 1.0, 2.0)],
                frame_grid=True,
                grid_rows=3,
                grid_cols=3,
                structure_job_id="job123",
            ),
            str(video),
        )

        assert result.staging_dir == str(staging_dir)
        assert result.video_hash == "hash123"
        assert len(result.scenes) == 2
        # write_staging 真实执行 → manifest 已落盘
        assert (staging_dir / "manifest.json").is_file()
        # frame_extract 的 Mock 返回 grid_image，但 grid 文件是 mock 的，不落盘
        extract.assert_called_once()

    @pytest.mark.asyncio
    async def test_requires_structure_job_id(self, monkeypatch, tmp_path: Path):
        from shared.core.errors.exceptions import ApiException

        video = tmp_path / "demo.mp4"
        video.write_bytes(b"fake-video")
        monkeypatch.setattr(
            "structure.services.video.pipeline.settings",
            _settings(tmp_path),
        )
        monkeypatch.setattr(
            "structure.services.video.pipeline.compute_video_hash",
            lambda _path: "hash123",
        )
        monkeypatch.setattr(
            "structure.services.video.pipeline.extract_metadata",
            lambda _path: _metadata(),
        )

        with pytest.raises(ApiException):
            await structure(
                StructureCommand(
                    video_path="demo.mp4",
                    scenes=[_boundary(0, 0, 24, 0.0, 1.0)],
                    frame_grid=False,
                ),
                str(video),
            )
