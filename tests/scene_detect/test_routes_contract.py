import pytest
from fastapi import BackgroundTasks

from scene_detect.api.endpoints.detect import detect_scene
from scene_detect.api.routes import router
from scene_detect.schemas.scene import DetectTaskRequest
from shared.task_status import TaskStatusDTO


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
    monkeypatch.setattr(
        "scene_detect.api.endpoints.detect.create_task",
        lambda **_kwargs: TaskStatusDTO(
            task_id="generated-task-1",
            asset_id="asset-1",
            task_type="scene_detect",
            status="queued",
            created_at=1,
            updated_at=1,
        ),
    )

    response = await detect_scene(
        DetectTaskRequest(
            asset_id="asset-1",
            video_path=str(video),
        ),
        BackgroundTasks(),
    )

    assert response.data is not None
    assert response.data.task_id == "generated-task-1"
    assert response.data.status == "queued"
