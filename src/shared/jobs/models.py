"""jobs 表 schema 与 CRUD 操作。

jobs 表与 Huey 共用同一 SQLite 文件，API 通过该表查询任务状态。
"""

from __future__ import annotations

import json
import time
import uuid
from logging import getLogger

from shared.jobs.settings import settings

logger = getLogger(__name__)

# ── SQL ──────────────────────────────────────────────────────────────────

# 注意：ALTER TABLE ADD COLUMN 会把列加在末尾；查询一律用显式列名，不依赖物理顺序。
SQL_CREATE_JOBS_TABLE = """
CREATE TABLE IF NOT EXISTS jobs (
    job_id       TEXT PRIMARY KEY,
    job_type     TEXT NOT NULL,
    video_hash   TEXT,
    status       TEXT NOT NULL DEFAULT 'queued',
    created_at   INTEGER NOT NULL,
    started_at   INTEGER,
    finished_at  INTEGER,
    attempt      INTEGER NOT NULL DEFAULT 0,
    progress     TEXT,
    request_json TEXT NOT NULL,
    result_json  TEXT,
    result_ref   TEXT,
    error_code   TEXT,
    error_message TEXT,
    error_detail TEXT
)
"""

SQL_CREATE_PENDING_INDEX = """
CREATE INDEX IF NOT EXISTS idx_jobs_pending_video
ON jobs(job_type, video_hash)
WHERE status IN ('queued', 'running')
"""

SQL_INSERT_JOB = """
INSERT INTO jobs (job_id, job_type, video_hash, status, created_at, attempt, request_json)
VALUES (?, ?, ?, 'queued', ?, 0, ?)
"""

SQL_GET_JOB = """
SELECT job_id, job_type, video_hash, status, created_at, started_at, finished_at,
       attempt, progress, request_json, result_json, result_ref,
       error_code, error_message, error_detail
FROM jobs WHERE job_id = ?
"""

SQL_GET_PENDING_JOB_BY_VIDEO_HASH = """
SELECT job_id FROM jobs
WHERE job_type = ?
  AND video_hash = ?
  AND status IN ('queued', 'running')
ORDER BY created_at DESC
LIMIT 1
"""

SQL_UPDATE_STATUS_TPL = """
UPDATE jobs
SET status = COALESCE(?, status),
    started_at  = COALESCE(?, started_at),
    finished_at = COALESCE(?, finished_at),
    attempt     = COALESCE(?, attempt),
    progress    = COALESCE(?, progress),
    result_json = COALESCE(?, result_json),
    result_ref  = COALESCE(?, result_ref),
    error_code  = COALESCE(?, error_code),
    error_message = COALESCE(?, error_message),
    error_detail  = COALESCE(?, error_detail)
WHERE job_id = ?
"""

SQL_CLEANUP_EXPIRED = """
DELETE FROM jobs
WHERE status IN ('succeeded', 'failed')
  AND finished_at < ?
  AND job_id NOT IN (
    SELECT DISTINCT json_extract(request_json, '$.detect_job_id')
    FROM jobs
    WHERE job_type = 'structure'
      AND json_extract(request_json, '$.detect_job_id') IS NOT NULL
  )
  AND job_id NOT IN (
    SELECT DISTINCT json_extract(request_json, '$.structure_job_id')
    FROM jobs
    WHERE job_type = 'describe'
      AND json_extract(request_json, '$.structure_job_id') IS NOT NULL
  )
"""

SQL_GET_DESCRIBE_STATUS = """
SELECT status FROM jobs
WHERE job_type = 'describe'
  AND video_hash = ?
ORDER BY created_at DESC
LIMIT 1
"""

# ── Public helpers ───────────────────────────────────────────────────────


def _now() -> int:
    return int(time.time())


def _db():
    """获取 Huey storage 的 db() 上下文管理器（线程安全，带 self.lock + begin exclusive）。"""
    from shared.jobs.huey import huey

    return huey.storage.db


def _has_column(curs, table: str, column: str) -> bool:
    rows = curs.execute(f"PRAGMA table_info({table})").fetchall()  # noqa: S608
    return any(r[1] == column for r in rows)


def init_db() -> None:
    """初始化 jobs 表（幂等）。应用启动时调用。

    兼容已有库：CREATE TABLE IF NOT EXISTS 不会给旧表加列，
    因此额外用 ALTER TABLE 迁移 video_hash。
    """
    with _db()(commit=True) as curs:
        curs.execute(SQL_CREATE_JOBS_TABLE)
        if not _has_column(curs, "jobs", "video_hash"):
            curs.execute("ALTER TABLE jobs ADD COLUMN video_hash TEXT")
            logger.info("jobs 表已迁移：新增 video_hash 列")
        if not _has_column(curs, "jobs", "progress"):
            curs.execute("ALTER TABLE jobs ADD COLUMN progress TEXT")
            logger.info("jobs 表已迁移：新增 progress 列")
        curs.execute(SQL_CREATE_PENDING_INDEX)
    logger.info("jobs 表已就绪 (db=%s)", settings.huey_db_path)


def create_job(
    job_type: str,
    request_json: dict,
    *,
    job_id: str | None = None,
    video_hash: str | None = None,
) -> str:
    """创建 jobs 行并返回 job_id（UUID）。"""
    jid = job_id or str(uuid.uuid4())
    with _db()(commit=True) as curs:
        curs.execute(
            SQL_INSERT_JOB,
            (
                jid,
                job_type,
                video_hash,
                _now(),
                json.dumps(request_json, ensure_ascii=False),
            ),
        )
    logger.debug("创建 job: id=%s type=%s hash=%s", jid, job_type, video_hash)
    return jid


def get_job(job_id: str) -> dict | None:
    """按 job_id 查询 jobs 表，返回行 dict 或 None。"""
    with _db()() as curs:
        row = curs.execute(SQL_GET_JOB, (job_id,)).fetchone()
    if row is None:
        return None
    return _row_to_dict(row)


def get_pending_job_by_video_hash(job_type: str, video_hash: str) -> str | None:
    """查询指定 job_type + video_hash 且状态为 queued/running 的 job_id。

    用于提交任务前的去重校验。
    """
    if not video_hash:
        return None
    with _db()() as curs:
        row = curs.execute(SQL_GET_PENDING_JOB_BY_VIDEO_HASH, (job_type, video_hash)).fetchone()
    return row[0] if row else None


def get_describe_status(structure_job_id: str) -> str:
    """查询最新 describe job 状态：none | pending | succeeded | failed。"""
    with _db()() as curs:
        row = curs.execute(
            SQL_GET_DESCRIBE_STATUS,
            (structure_job_id,),
        ).fetchone()
    if row is None:
        return "none"
    status = row[0]
    return "pending" if status in ("queued", "running") else status


_JOB_COLUMNS = [
    "job_id",
    "job_type",
    "video_hash",
    "status",
    "created_at",
    "started_at",
    "finished_at",
    "attempt",
    "progress",
    "request_json",
    "result_json",
    "result_ref",
    "error_code",
    "error_message",
    "error_detail",
]


def _row_to_dict(row) -> dict:
    return dict(zip(_JOB_COLUMNS, row, strict=True))


def _serialize(val) -> str | None:
    """dict → JSON 字符串，其他值原样返回。"""
    if val is None:
        return None
    if isinstance(val, dict | list):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


def update_job(job_id: str, **kwargs) -> None:
    """更新 job 的指定字段。

    支持的 kwargs 键：
        status, started_at, finished_at, attempt, progress,
        result_json, result_ref,
        error_code, error_message, error_detail

    其中 result_json / result_ref 可传 dict，自动序列化为 JSON 字符串。
    """
    params = tuple(
        _serialize(kwargs.get(k))
        for k in (
            "status",
            "started_at",
            "finished_at",
            "attempt",
            "progress",
            "result_json",
            "result_ref",
            "error_code",
            "error_message",
            "error_detail",
        )
    )
    with _db()(commit=True) as curs:
        curs.execute(SQL_UPDATE_STATUS_TPL, (*params, job_id))


def cleanup_expired_jobs(max_age_days: int | None = None) -> int:
    """删除超过 TTL 的已完成 job 行（被引用的 scene_detect 除外）。

    Args:
        max_age_days: TTL 天数，默认 settings.job_ttl_days。0 或 None 不清理。

    Returns:
        删除的行数。
    """
    ttl = max_age_days if max_age_days is not None else settings.job_ttl_days
    if ttl <= 0:
        return 0

    deadline = _now() - ttl * 86400
    with _db()(commit=True) as curs:
        curs.execute(SQL_CLEANUP_EXPIRED, (deadline,))
        deleted = curs.rowcount
    if deleted:
        logger.info("TTL 清理: 删除了 %d 行 (finished_at < %d)", deleted, deadline)
    return deleted
