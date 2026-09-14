"""Huey 任务队列管理 CLI。

用法：
    # TTL 清理（默认 7 天）
    python -m shared.jobs cleanup

    # 指定 TTL 天数
    python -m shared.jobs cleanup --max-age 14

    # 同时清理 structure 未搬走的 staging 产物（TTL 默认 settings.staging_ttl_sec）
    python -m shared.jobs cleanup --structure-staging
"""

from __future__ import annotations

import argparse
from logging import getLogger

from shared.jobs import _pending_describe_staging_dirs, init_db
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
    cl.add_argument(
        "--structure-staging",
        action="store_true",
        help="同时清理 structure 超过 TTL 未被搬走的 staging 产物",
    )

    args = parser.parse_args()

    if args.command == "cleanup":
        init_db()
        deleted = cleanup_expired_jobs(max_age_days=args.max_age)
        logger.info(f"jobs 表清理: 删除了 {deleted} 行")

        if args.structure_staging:
            from structure.core.settings import settings as struct_settings
            from structure.services.video.cache import cleanup_expired_staging

            removed = cleanup_expired_staging(
                struct_settings, protected=_pending_describe_staging_dirs()
            )
            logger.info(f"structure staging 清理: 删除了 {removed} 个目录")


if __name__ == "__main__":
    main()
