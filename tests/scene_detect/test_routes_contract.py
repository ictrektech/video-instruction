import pytest
from fastapi import BackgroundTasks

from scene_detect.api.endpoints.detect import detect_scene
from scene_detect.api.routes import router
from scene_detect.schemas.scene import DetectTaskRequest


def test_scene_detect_exposes_async_v1_routes_without_v2_jobs():
    paths = {route.path for route in router.routes}

    assert "/api/v1/scenes/detect" in paths
    assert "/api/v1/scenes/detect/tasks/{task_id}" in paths
    assert not any(path.startswith("/v2/") for path in paths)


@pytest.mark.asyncio
async def test_detect_submit_accepts_task_without_callback(monkeypatch, tmp_path):
    video = tmp_path / "demo.mp4"
    video.write_bytes(b"fake")
    monkeypatch.setattr(
        "scene_detect.api.endpoints.detect.resolve_video_path",
        lambda video_path, _base_path: video_path,
    )

    response = await detect_scene(
        DetectTaskRequest(
            task_id="task-1",
            asset_id="asset-1",
            video_path=str(video),
        ),
        BackgroundTasks(),
    )

    assert response.data is not None
    assert response.data.status == "accepted"
