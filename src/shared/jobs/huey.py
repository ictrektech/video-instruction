"""共享 SqliteHuey 实例。

两个服务共用同一个 huey.db，通过 @huey.task() 装饰器注册任务函数。
Huey 的 task 表作为队列，kv 表存放结果/错误，schedule 表存放定时任务。

使用方式：
    from shared.jobs.huey import huey

    @huey.task(context=True)
    def my_task(job_id: str, ...):
        ...
"""

from pathlib import Path

from huey import SqliteHuey

from shared.jobs.settings import settings

_db_path = Path(settings.huey_db_path)
_db_path.parent.mkdir(parents=True, exist_ok=True)

huey = SqliteHuey(
    "video-instruction",
    filename=str(_db_path),
    results=True,
    store_none=False,
    store_intermediate_errors=True,
    utc=True,
)
