"""artifact 交付：tar 流与 staging 释放。

- ``GET /structure/jobs/{id}/artifact`` 返回 tar（manifest.json、grids/**、descriptions.json[可选]）
- ``DELETE /structure/jobs/{id}`` 显式释放 staging，幂等
"""

from __future__ import annotations

import shutil
import tarfile
import tempfile
from logging import getLogger
from pathlib import Path
from typing import IO, Any

from shared.jobs import get_describe_status
from structure.services.video.cache import (
    DESCRIPTIONS_FILENAME,
    GRIDS_DIRNAME,
    MANIFEST_FILENAME,
    get_descriptions_path,
    get_grids_dir,
    get_manifest_path,
    staging_dir_from_row,
)

logger = getLogger(__name__)


def _scan_entries(staging_dir: Path) -> list[dict]:
    """扫描 artifact 交付文件：manifest.json + grids/** + descriptions.json（如存在）。

    metadata.json 不纳入 artifact（与 manifest 冗余）；隐藏/临时文件不纳入。
    """
    entries: list[dict] = []

    def _add(path: Path, arcname: str) -> None:
        try:
            st = path.stat()
        except OSError:
            return
        entries.append({"path": arcname, "size": st.st_size})

    manifest = get_manifest_path(staging_dir)
    if manifest.is_file():
        _add(manifest, MANIFEST_FILENAME)

    grids = get_grids_dir(staging_dir)
    if grids.is_dir():
        for p in sorted(grids.iterdir()):
            if p.is_file() and not p.name.startswith("."):
                _add(p, f"{GRIDS_DIRNAME}/{p.name}")

    descriptions = get_descriptions_path(staging_dir)
    if descriptions.is_file():
        _add(descriptions, DESCRIPTIONS_FILENAME)

    return entries


def build_artifact_info(staging_dir: Path, structure_job_id: str) -> dict[str, Any] | None:
    """构建 artifact 清单。"""
    if not staging_dir.is_dir():
        return None

    entries = _scan_entries(staging_dir)
    if not entries:
        return None

    describe_status = get_describe_status(structure_job_id)
    # 只有 describe succeeded 才把 descriptions.json 纳入 artifact；
    # failed/none 即使残留旧文件也不下发，避免客户端拿到与 describe_status 矛盾的内容。
    if describe_status != "succeeded":
        entries = [e for e in entries if e["path"] != DESCRIPTIONS_FILENAME]
    if not entries:
        return None

    return {
        "describe_status": describe_status,
        "total_bytes": sum(e["size"] for e in entries),
        "files": [{"path": e["path"], "size": e["size"]} for e in entries],
    }


def build_status_artifact_info(row: dict) -> dict[str, Any] | None:
    """状态轮询用的轻量 artifact 块；未冻结/已释放返回 None。"""
    if row.get("status") != "succeeded":
        return None
    staging = staging_dir_from_row(row)
    if staging is None or not staging.is_dir():
        return None
    structure_job_id = row["job_id"]
    if get_describe_status(structure_job_id) == "pending":
        return None
    return build_artifact_info(staging, structure_job_id)


def _write_tar(staging_dir: Path, files: list[dict], fileobj: IO[bytes]) -> None:
    with tarfile.open(fileobj=fileobj, mode="w") as tar:
        for item in files:
            path = staging_dir / item["path"]
            if path.is_file():
                tar.add(path, arcname=item["path"])


def build_artifact_download(
    staging_dir: Path,
    structure_job_id: str,
) -> tuple[dict, str | None] | None:
    """生成 artifact 清单与 tar 临时文件路径；describe pending 时不生成 tar。"""
    if not staging_dir.is_dir():
        return None
    info = build_artifact_info(staging_dir, structure_job_id)
    if info is None:
        return None
    if info["describe_status"] == "pending":
        return info, None
    tmp_path: str | None = None
    try:
        with tempfile.NamedTemporaryFile(delete=False, suffix=".tar") as tmp:
            tmp_path = tmp.name
            _write_tar(staging_dir, info["files"], tmp)
    except FileNotFoundError:
        # 与 DELETE/TTL 竞态：目录在生成期间被释放
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        return None
    except Exception:
        if tmp_path is not None:
            Path(tmp_path).unlink(missing_ok=True)
        raise
    if tmp_path is None:  # pragma: no cover - NamedTemporaryFile 成功时必然赋值
        return None
    return info, tmp_path


def release_staging(staging_dir: Path) -> None:
    """释放 staging 目录；目录不存在时幂等。"""
    try:
        shutil.rmtree(staging_dir)
    except FileNotFoundError:
        pass
    except OSError as exc:
        logger.warning("staging 释放失败（交由 TTL 清理）: %s (%s)", staging_dir, exc)
