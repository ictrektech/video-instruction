"""artifact 交付：tar 流与 staging 释放的单元测试。"""

from __future__ import annotations

import json
import tarfile
from pathlib import Path

from structure.services.video import artifact as artifact_service
from structure.services.video.cache import (
    DESCRIPTIONS_FILENAME,
    GRIDS_DIRNAME,
    MANIFEST_FILENAME,
    METADATA_FILENAME,
)


def _staging(tmp_path: Path, *, with_descriptions: bool = True) -> Path:
    staging = tmp_path / "staging" / "job123"
    staging.mkdir(parents=True)
    (staging / MANIFEST_FILENAME).write_text('{"video_hash": "hash123"}', encoding="utf-8")
    (staging / METADATA_FILENAME).write_text("{}", encoding="utf-8")
    grids = staging / GRIDS_DIRNAME
    grids.mkdir()
    (grids / "scene_001.jpg").write_bytes(b"grid-jpg")
    (grids / ".hidden").write_bytes(b"hidden")
    if with_descriptions:
        (staging / DESCRIPTIONS_FILENAME).write_text('{"descriptions": []}', encoding="utf-8")
    return staging


def _row(staging_dir: Path) -> dict:
    return {
        "job_id": "job123",
        "job_type": "structure",
        "status": "succeeded",
        "result_ref": json.dumps({"staging_dir": str(staging_dir)}),
    }


def test_staging_dir_from_row(tmp_path: Path):
    staging = _staging(tmp_path)
    row = _row(staging)
    assert artifact_service.staging_dir_from_row(row) == staging


def test_scan_entries_excludes_metadata_and_hidden(tmp_path: Path):
    staging = _staging(tmp_path)
    entries = artifact_service._scan_entries(staging)
    paths = {e["path"] for e in entries}
    assert paths == {
        MANIFEST_FILENAME,
        f"{GRIDS_DIRNAME}/scene_001.jpg",
        DESCRIPTIONS_FILENAME,
    }
    assert METADATA_FILENAME not in paths


def test_build_artifact_info_lists_files(tmp_path: Path, monkeypatch):
    staging = _staging(tmp_path)
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "succeeded")

    info = artifact_service.build_artifact_info(staging, "job123")
    assert info is not None
    assert info["describe_status"] == "succeeded"
    assert all("sha256" not in item for item in info["files"])


def test_describe_failed_excludes_descriptions_even_if_file_exists(tmp_path: Path, monkeypatch):
    staging = _staging(tmp_path)
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "failed")
    info = artifact_service.build_artifact_info(staging, "job123")
    assert info is not None
    assert info["describe_status"] == "failed"
    assert DESCRIPTIONS_FILENAME not in {item["path"] for item in info["files"]}


def test_build_artifact_download_returns_tar(tmp_path: Path, monkeypatch):
    staging = _staging(tmp_path)
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "succeeded")

    result = artifact_service.build_artifact_download(staging, "job123")
    assert result is not None
    info, tar_path = result
    assert info["total_bytes"] > 0
    assert tar_path is not None

    with tarfile.open(tar_path, mode="r") as tar:
        names = set(tar.getnames())
    Path(tar_path).unlink(missing_ok=True)
    assert MANIFEST_FILENAME in names
    assert f"{GRIDS_DIRNAME}/scene_001.jpg" in names
    assert DESCRIPTIONS_FILENAME in names
    assert METADATA_FILENAME not in names


def test_build_artifact_download_missing_dir_returns_none(tmp_path: Path, monkeypatch):
    missing = tmp_path / "missing"
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "none")
    assert artifact_service.build_artifact_download(missing, "job123") is None


def test_build_artifact_download_pending_returns_no_tar(tmp_path: Path, monkeypatch):
    staging = _staging(tmp_path)
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "pending")
    result = artifact_service.build_artifact_download(staging, "job123")
    assert result is not None
    info, tar_path = result
    assert info["describe_status"] == "pending"
    assert tar_path is None


def test_release_staging_idempotent(tmp_path: Path):
    staging = _staging(tmp_path)
    artifact_service.release_staging(staging)
    assert not staging.exists()
    artifact_service.release_staging(staging)  # 第二次不报错


def test_build_status_artifact_info_pending_returns_none(tmp_path: Path, monkeypatch):
    staging = _staging(tmp_path)
    row = _row(staging)
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "pending")
    assert artifact_service.build_status_artifact_info(row) is None


def test_build_status_artifact_info_returns_info(tmp_path: Path, monkeypatch):
    staging = _staging(tmp_path)
    row = _row(staging)
    monkeypatch.setattr(artifact_service, "get_describe_status", lambda _job_id: "none")
    info = artifact_service.build_status_artifact_info(row)
    assert info is not None
    assert info["describe_status"] == "none"


def test_build_status_artifact_info_released_returns_none(tmp_path: Path):
    staging = _staging(tmp_path)
    row = _row(staging)
    artifact_service.release_staging(staging)
    assert artifact_service.build_status_artifact_info(row) is None
