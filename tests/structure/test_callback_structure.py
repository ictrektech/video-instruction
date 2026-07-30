from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

from structure.api.routes import router
from structure.schemas.video import (
    SceneBoundaryInput,
    StructureCallbackEvent,
    StructureCommand,
    StructureResultDTO,
    VideoMetadataSchema,
)
from structure.services.video.callback import _encode_multipart
from structure.services.video.pipeline import structure


def _boundary() -> SceneBoundaryInput:
    return SceneBoundaryInput(
        scene_index=0,
        start_frame=0,
        end_frame=24,
        start_time=0.0,
        end_time=1.0,
    )


def _metadata() -> dict:
    return {
        "fps": 25.0,
        "duration": 1.0,
        "width": 1280,
        "height": 720,
        "codec": "h264",
        "bitrate": 1000,
        "has_audio": False,
        "total_frames": 25,
    }


def test_structure_exposes_callback_submit_without_v2_or_cache_routes():
    paths = {route.path for route in router.routes}

    assert "/api/v1/video/structure" in paths
    assert "/api/v1/video/cache" not in paths
    assert not any(path.startswith("/v2/") for path in paths)


@pytest.mark.asyncio
async def test_structure_writes_grid_to_explicit_output_dir(monkeypatch, tmp_path: Path):
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"fake-video")
    output_dir = tmp_path / "callback-grids"

    settings_stub = SimpleNamespace(
        video_work_dir=str(tmp_path / "work"),
        video_grid_tile_max_height=180,
        video_ffmpeg_timeout=60,
    )
    monkeypatch.setattr("structure.services.video.pipeline.settings", settings_stub)
    monkeypatch.setattr(
        "structure.services.video.pipeline.compute_video_hash",
        lambda _path: "hash123",
    )
    monkeypatch.setattr(
        "structure.services.video.pipeline.extract_metadata",
        lambda _path: _metadata(),
    )

    def fake_extract_scene_grids(
        _video_path,
        scene_bounds,
        _metadata_value,
        _work_dir,
        _tile_max_height,
        _grid_rows,
        _grid_cols,
        _cache_dir,
        grid_output_dir,
        _ffmpeg_timeout,
    ):
        grid_output_dir.mkdir(parents=True, exist_ok=True)
        (grid_output_dir / "scene_001.jpg").write_bytes(b"jpeg")
        scene = scene_bounds[0]
        from structure.schemas.video import SceneDTO

        return [
            (
                SceneDTO(
                    scene_id="scene_abc",
                    scene_index=0,
                    start_frame=scene[0],
                    end_frame=scene[1],
                    start_time=scene[2],
                    end_time=scene[3],
                    grid_image="scene_001.jpg",
                ),
                [],
            )
        ]

    monkeypatch.setattr(
        "structure.services.video.pipeline.extract_scene_grids",
        fake_extract_scene_grids,
    )

    result = await structure(
        StructureCommand(
            video_path="demo.mp4",
            scenes=[_boundary()],
            frame_grid=True,
        ),
        str(video),
        grid_output_dir=output_dir,
    )

    assert result.video_hash == "hash123"
    assert result.grid_base_path == str(output_dir)
    assert result.scenes[0].grid_image == "scene_001.jpg"
    assert (output_dir / "scene_001.jpg").read_bytes() == b"jpeg"


def test_multipart_callback_contains_event_and_binary_file():
    event = StructureCallbackEvent(
        task_id="task-1",
        asset_id="asset-1",
        status="succeeded",
        result=StructureResultDTO(
            video_hash="hash123",
            metadata=VideoMetadataSchema(video_path="demo.mp4"),
            scenes=[],
        ),
    )

    body, content_type = _encode_multipart(
        event,
        [("scene_001", "scene_001.jpg", b"jpeg-data", "image/jpeg")],
    )

    assert content_type.startswith("multipart/form-data; boundary=")
    assert b'name="event"' in body
    assert b'"status": "succeeded"' in body
    assert b'name="scene_001"; filename="scene_001.jpg"' in body
    assert b"jpeg-data" in body
