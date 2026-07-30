from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from shared.core.errors.error_codes import BusinessErrorCode
from shared.core.errors.exceptions import ApiException


class TaskStatusDTO(BaseModel):
    """SQLite-backed task status for async APIs."""

    task_id: str = Field(description="服务生成的任务 ID")
    asset_id: str = Field(default="", description="调用方资产 ID")
    task_type: str = Field(description="任务类型")
    status: str = Field(description="任务状态: queued/running/succeeded/failed")
    stage: str = Field(default="", description="当前阶段")
    progress: float | None = Field(default=None, description="任务进度，0-1")
    message: str = Field(default="", description="状态消息")
    error: dict[str, str] | None = Field(default=None, description="失败信息")
    result: dict[str, Any] | None = Field(default=None, description="成功结果，不包含二进制文件")
    created_at: int = Field(description="创建时间 Unix 秒时间戳")
    updated_at: int = Field(description="更新时间 Unix 秒时间戳")


_SCHEMA_INITIALIZED = False
_CLEANED_TYPES: set[str] = set()


def _settings_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw == "":
        return default
    return int(raw)


def task_db_path() -> Path:
    return Path(os.getenv("TASK_DB_PATH", "data/tasks/tasks.db"))


def max_concurrency() -> int:
    return _settings_int("TASK_MAX_CONCURRENCY", 2)


def queue_limit() -> int:
    return _settings_int("TASK_QUEUE_LIMIT", 20)


def result_ttl_sec() -> int:
    return _settings_int("TASK_RESULT_TTL_SEC", 3600)


@contextmanager
def _db(commit: bool = False):
    init_task_db()
    path = task_db_path()
    conn = sqlite3.connect(path, timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=30000")
        yield conn
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    finally:
        conn.close()


def init_task_db(task_type: str | None = None) -> None:
    global _SCHEMA_INITIALIZED
    path = task_db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path, timeout=30)
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        if not _SCHEMA_INITIALIZED:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS video_tasks (
                  task_id TEXT PRIMARY KEY,
                  task_type TEXT NOT NULL,
                  asset_id TEXT NOT NULL DEFAULT '',
                  status TEXT NOT NULL,
                  stage TEXT NOT NULL DEFAULT '',
                  progress REAL,
                  message TEXT NOT NULL DEFAULT '',
                  error_json TEXT,
                  result_json TEXT,
                  request_json TEXT,
                  created_at INTEGER NOT NULL,
                  updated_at INTEGER NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_video_tasks_type_status_created "
                "ON video_tasks(task_type, status, created_at)"
            )
            _SCHEMA_INITIALIZED = True
        # This service does not resume tasks after restart.  Drop stale active rows for
        # the current service only; scene-detect and structure may share one SQLite file.
        if task_type is not None and task_type not in _CLEANED_TYPES:
            conn.execute(
                "DELETE FROM video_tasks WHERE task_type=? AND status IN ('queued', 'running')",
                (task_type,),
            )
            _CLEANED_TYPES.add(task_type)
        conn.commit()
    finally:
        conn.close()


def create_task(
    *,
    task_type: str,
    asset_id: str,
    request: dict[str, Any],
) -> TaskStatusDTO:
    prune_expired_terminal_tasks()
    task_id = str(uuid.uuid4())
    now = int(time.time())
    request_json = json.dumps(request, ensure_ascii=False)
    with _db(commit=True) as conn:
        active_count = conn.execute(
            """
            SELECT COUNT(*) FROM video_tasks
            WHERE task_type=? AND status IN ('queued', 'running')
            """,
            (task_type,),
        ).fetchone()[0]
        if active_count >= queue_limit():
            raise ApiException(
                BusinessErrorCode.COMMON_UNSUPPORTED_OPERATION,
                f"任务队列已满: limit={queue_limit()}",
            )
        conn.execute(
            """
            INSERT INTO video_tasks (
              task_id, task_type, asset_id, status, stage, progress, message,
              request_json, created_at, updated_at
            )
            VALUES (?, ?, ?, 'queued', 'queued', 0, ?, ?, ?, ?)
            """,
            (
                task_id,
                task_type,
                asset_id,
                f"{task_type} task queued",
                request_json,
                now,
                now,
            ),
        )
    return require_task_status(task_id)


def wait_for_turn(task_id: str, task_type: str, poll_sec: float = 0.5) -> bool:
    while True:
        if try_claim_task(task_id, task_type):
            return True
        status = get_task_status(task_id, consume_terminal=False)
        if status is None or status.status != "queued":
            return False
        time.sleep(poll_sec)


def try_claim_task(task_id: str, task_type: str) -> bool:
    now = int(time.time())
    with _db(commit=True) as conn:
        conn.execute("BEGIN IMMEDIATE")
        row = conn.execute(
            "SELECT status FROM video_tasks WHERE task_id=? AND task_type=?",
            (task_id, task_type),
        ).fetchone()
        if row is None or row["status"] != "queued":
            return False
        first = conn.execute(
            """
            SELECT task_id FROM video_tasks
            WHERE task_type=? AND status='queued'
            ORDER BY created_at ASC, rowid ASC
            LIMIT 1
            """,
            (task_type,),
        ).fetchone()
        if first is None or first["task_id"] != task_id:
            return False
        running_count = conn.execute(
            "SELECT COUNT(*) FROM video_tasks WHERE task_type=? AND status='running'",
            (task_type,),
        ).fetchone()[0]
        if running_count >= max_concurrency():
            return False
        conn.execute(
            """
            UPDATE video_tasks
            SET status='running', stage='running', progress=0, message=?, updated_at=?
            WHERE task_id=?
            """,
            (f"{task_type} task running", now, task_id),
        )
        return True


def set_task_status(
    task_id: str,
    *,
    task_type: str,
    asset_id: str = "",
    status: str,
    stage: str = "",
    progress: float | None = None,
    message: str = "",
    error: dict[str, str] | None = None,
    result: dict[str, Any] | None = None,
) -> TaskStatusDTO | None:
    now = int(time.time())
    current = require_task_status(task_id)
    if status in {"succeeded", "failed"} and _is_result_expired(current.created_at, now):
        delete_task(task_id)
        return None
    with _db(commit=True) as conn:
        conn.execute(
            """
            UPDATE video_tasks
            SET asset_id=?, status=?, stage=?, progress=?, message=?,
                error_json=?, result_json=?, updated_at=?
            WHERE task_id=?
            """,
            (
                asset_id or current.asset_id,
                status,
                stage,
                progress,
                message,
                json.dumps(error, ensure_ascii=False) if error is not None else None,
                json.dumps(result, ensure_ascii=False) if result is not None else None,
                now,
                task_id,
            ),
        )
    return require_task_status(task_id)


def get_task_status(task_id: str, *, consume_terminal: bool = True) -> TaskStatusDTO | None:
    prune_expired_terminal_tasks()
    with _db() as conn:
        row = conn.execute("SELECT * FROM video_tasks WHERE task_id=?", (task_id,)).fetchone()
    if row is None:
        return None
    dto = _row_to_dto(row)
    if dto.status in {"succeeded", "failed"} and consume_terminal:
        delete_task(task_id)
    return dto


def require_task_status(task_id: str) -> TaskStatusDTO:
    status = get_task_status(task_id, consume_terminal=False)
    if status is None:
        raise ApiException(BusinessErrorCode.JOB_NOT_FOUND, f"task_id={task_id}")
    return status


def delete_task(task_id: str) -> None:
    with _db(commit=True) as conn:
        conn.execute("DELETE FROM video_tasks WHERE task_id=?", (task_id,))


def prune_expired_terminal_tasks() -> None:
    ttl = result_ttl_sec()
    if ttl <= 0:
        return
    cutoff = int(time.time()) - ttl
    with _db(commit=True) as conn:
        conn.execute(
            "DELETE FROM video_tasks WHERE status IN ('succeeded', 'failed') AND updated_at < ?",
            (cutoff,),
        )


def _is_result_expired(created_at: int, now: int) -> bool:
    ttl = result_ttl_sec()
    return ttl > 0 and now - created_at >= ttl


def _row_to_dto(row: sqlite3.Row) -> TaskStatusDTO:
    return TaskStatusDTO(
        task_id=row["task_id"],
        asset_id=row["asset_id"],
        task_type=row["task_type"],
        status=row["status"],
        stage=row["stage"],
        progress=row["progress"],
        message=row["message"],
        error=json.loads(row["error_json"]) if row["error_json"] else None,
        result=json.loads(row["result_json"]) if row["result_json"] else None,
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
