from __future__ import annotations

import pytest

from shared import task_status
from shared.core.errors.exceptions import ApiException


@pytest.fixture
def task_db(monkeypatch, tmp_path):
    monkeypatch.setenv("TASK_DB_PATH", str(tmp_path / "tasks.db"))
    monkeypatch.setenv("TASK_QUEUE_LIMIT", "2")
    monkeypatch.setenv("TASK_MAX_CONCURRENCY", "1")
    monkeypatch.setenv("TASK_RESULT_TTL_SEC", "3600")
    monkeypatch.setattr(task_status, "_SCHEMA_INITIALIZED", False)
    monkeypatch.setattr(task_status, "_CLEANED_TYPES", set())
    task_status.init_task_db("scene_detect")


def test_create_task_rejects_when_queue_is_full(task_db, monkeypatch):
    monkeypatch.setenv("TASK_QUEUE_LIMIT", "1")

    first = task_status.create_task(
        task_type="scene_detect",
        asset_id="asset-1",
        request={"video_path": "a.mp4"},
    )

    assert first.status == "queued"
    with pytest.raises(ApiException):
        task_status.create_task(
            task_type="scene_detect",
            asset_id="asset-2",
            request={"video_path": "b.mp4"},
        )


def test_try_claim_task_respects_per_type_concurrency(task_db):
    first = task_status.create_task(
        task_type="scene_detect",
        asset_id="asset-1",
        request={"video_path": "a.mp4"},
    )
    second = task_status.create_task(
        task_type="scene_detect",
        asset_id="asset-2",
        request={"video_path": "b.mp4"},
    )

    assert task_status.try_claim_task(first.task_id, "scene_detect")
    assert not task_status.try_claim_task(second.task_id, "scene_detect")


def test_terminal_status_is_consumed_on_get(task_db):
    task = task_status.create_task(
        task_type="scene_detect",
        asset_id="asset-1",
        request={"video_path": "a.mp4"},
    )
    task_status.try_claim_task(task.task_id, "scene_detect")
    task_status.set_task_status(
        task.task_id,
        task_type="scene_detect",
        status="succeeded",
        result={"scenes": []},
    )

    first_get = task_status.get_task_status(task.task_id)
    second_get = task_status.get_task_status(task.task_id)

    assert first_get is not None
    assert first_get.status == "succeeded"
    assert second_get is None
