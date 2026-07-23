"""Huey 任务队列管理 CLI。

用法：
    # TTL 清理（默认 7 天）
    python -m shared.jobs cleanup

    # 指定 TTL 天数
    python -m shared.jobs cleanup --max-age 14

    # 同时清理 Huey 过期结果
    python -m shared.jobs cleanup --sweep-results
"""

from __future__ import annotations

import argparse
from logging import getLogger

from shared.jobs import init_db
from shared.jobs.models import cleanup_expired_jobs

logger = getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(description="Huey 任务队列管理工具")
    sub = parser.add_subparsers(dest="command", required=True)

    # cleanup
    cl = sub.add_parser("cleanup", help="TTL 清理过期 job")
    cl.add_argument(
        "--max-age", type=int, default=None, help="TTL 天数（默认 settings.job_ttl_days）"
    )
    cl.add_argument("--sweep-results", action="store_true", help="同时清理 Huey 过期结果")

    args = parser.parse_args()

    if args.command == "cleanup":
        init_db()
        deleted = cleanup_expired_jobs(max_age_days=args.max_age)
        logger.info(f"jobs 表清理: 删除了 {deleted} 行")

        if args.sweep_results:
            from shared.jobs.huey import huey

            swept = huey.storage.sweep_results()
            logger.info(f"Huey 结果清理: 删除了 {swept} 条过期结果")


if __name__ == "__main__":
    main()
