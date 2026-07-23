"""shared/jobs — Huey 任务队列封装。

对外暴露：
- init_db()              — 初始化 jobs 表（应用启动时调用）
- create_job()           — 创建 jobs 行，返回 job_id
- get_job()              — 查询 job
- update_job()           — 更新 job 状态/结果/错误
- enqueue_job()          — 原子化：创建 jobs 行 + enqueue Huey task
- cleanup_expired()      — TTL 清理
- huey                   — 全局 SqliteHuey 实例（用于注册任务函数、enqueue、启动 Consumer）

用法：
    from shared.jobs import huey, init_db, enqueue_job, get_job

    # 应用启动
    init_db()

    # 提交任务（原子操作，自动生成 job_id）
    jid = enqueue_job("scene_detect", {"video_path": "..."}, run_detect.task_class,
                      task_args=(video_path,), task_kwargs={"threshold": 27.0})

    # 提交任务（指定 job_id）
    jid = enqueue_job("scene_detect", {"video_path": "..."}, run_detect.task_class,
                      task_args=(video_path,), job_id="my-uuid")
"""

from __future__ import annotations

import json
import uuid
from logging import getLogger

from shared.jobs.huey import huey
from shared.jobs.models import (
    SQL_INSERT_JOB,
    _db,
    _now,
    create_job,
    get_job,
    init_db,
    update_job,
)
from shared.jobs.models import (
    cleanup_expired_jobs as cleanup_expired,
)
from shared.jobs.schemas import JobErrorDTO, JobStatusResponse

logger = getLogger(__name__)

__all__ = [
    "huey",
    "init_db",
    "build_job_status_response",
    "create_job",
    "get_job",
    "update_job",
    "enqueue_job",
    "run_worker",
    "cleanup_expired",
]


def enqueue_job(
    job_type: str,
    request_json: dict,
    task_class: type,
    task_args: tuple = (),
    task_kwargs: dict | None = None,
    *,
    job_id: str | None = None,
    priority: int | None = None,
) -> str:
    """原子化：创建 jobs 行 + enqueue Huey task（在同一个事务中）。

    与分别调用 create_job() + huey.enqueue() 不同，此函数将两个操作
    放在同一个 ``begin exclusive`` 事务中，避免 create_job 成功但
    enqueue 失败导致的「僵尸 job」。

    Args:
        job_type: jobs.job_type 字段值（如 'scene_detect', 'structure'）。
        request_json: 任务请求参数的 dict，将 JSON 序列化存入 jobs.request_json。
        task_class: @huey.task() 装饰的 task_class（如 run_detect_scenes.task_class）。
        task_args: 传递给 task 函数的位置参数（**不包含 job_id**）。
            enqueue_job 会自动将 jid 作为第一个 positional arg 注入，
            因此 task 函数无需在 task_args 中重复传入 job_id。
        task_kwargs: 传递给 task 函数的关键字参数。
        job_id: 可选。指定 Huey Task ID + jobs.job_id（UUID），不指定则自动生成。
        priority: 可选。Huey task 优先级，不指定则使用 task_class 默认。

    Returns:
        job_id (UUID 字符串)。

    异常：
        任意异常都会回滚整个事务（jobs 行 + task 均不写入）。
    """
    jid = job_id or str(uuid.uuid4())

    # 构建 Huey Task 实例
    # 自动将 jid 作为第一个 positional arg 注入，使 task 函数能接收到 job_id
    resolved_kwargs = dict(task_kwargs) if task_kwargs else {}
    task = task_class(args=(jid,) + task_args, kwargs=resolved_kwargs, id=jid)

    # 通过 Huey 的 registry 序列化为 Message → 再序列化为 bytes
    message = huey._registry.create_message(task)
    data = huey.serializer.serialize(message)

    request_str = json.dumps(request_json, ensure_ascii=False)
    now_ts = _now()

    with _db()(commit=True) as curs:
        # 1. 写 jobs 表
        curs.execute(SQL_INSERT_JOB, (jid, job_type, now_ts, request_str))
        # 2. 写 Huey task 表（即 huey.storage.enqueue 的核心逻辑）
        curs.execute(
            "INSERT INTO task (queue, data, priority) VALUES (?, ?, ?)",
            (huey.name, memoryview(data), priority if priority is not None else 0),
        )

    logger.debug("enqueue_job: id=%s type=%s", jid, job_type)
    return jid


def run_worker(service: str) -> None:
    """启动 Huey Worker。两个 worker CLI 共用此函数。

    Args:
        service: "scene-detect" 或 "structure"，仅用于日志标识。
    """
    import argparse
    import signal
    import sys
    from logging import getLogger

    from scene_detect.services.tasks import TASKS as detect_tasks
    from structure.services.tasks import TASKS as structure_tasks

    logger = getLogger(__name__)

    parser = argparse.ArgumentParser(description=f"{service} Huey Worker")
    parser.add_argument("--workers", type=int, default=None, help="并行线程数（默认 4）")
    args = parser.parse_args()

    init_db()

    num_workers = args.workers or 4
    registered = detect_tasks + structure_tasks
    logger.info(
        "启动 %s worker: workers=%d tasks=%s",
        service,
        num_workers,
        [t.task_class.__name__ for t in registered],
    )

    # 覆盖 signal.signal 避免 Consumer 在非主线程注册信号处理器时报错
    original = signal.signal
    signal.signal = lambda _sig, _handler: original(signal.SIGINT, signal.SIG_DFL)

    from huey.consumer import Consumer

    consumer = Consumer(huey, workers=num_workers, worker_type="thread")
    try:
        consumer.run()
    except KeyboardInterrupt:
        logger.info("%s worker 已停止", service)
        sys.exit(0)


def build_job_status_response(row: dict) -> JobStatusResponse:
    """从 jobs 行构建统一的任务状态响应。

    两个 worker 的 GET /jobs/{id} 共用此函数，保证返回格式一致。
    """
    result = None
    if row["status"] == "succeeded" and row["result_json"]:
        try:
            result = json.loads(row["result_json"])
        except (json.JSONDecodeError, TypeError):
            logger.warning("解析 result_json 失败: job_id=%s", row["job_id"])

    error = None
    if row["status"] == "failed":
        error = JobErrorDTO(
            code=row["error_code"],
            message=row["error_message"],
            detail=row["error_detail"],
        )

    return JobStatusResponse(
        job_id=row["job_id"],
        type=row["job_type"],
        status=row["status"],
        created_at=row["created_at"],
        started_at=row["started_at"],
        finished_at=row["finished_at"],
        attempt=row["attempt"],
        result=result,
        error=error,
    )
