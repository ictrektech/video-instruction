import asyncio
import json
import sys
from collections.abc import AsyncGenerator
from datetime import datetime
from logging import getLogger

from sqlalchemy import event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session

from app.core.settings import settings

logger = getLogger(__name__)

engine = create_async_engine(
    settings.db_url,
    pool_pre_ping=True,
    json_serializer=lambda obj: json.dumps(obj, ensure_ascii=False),
    json_deserializer=json.loads,
)
async_session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)


async def init_db() -> None:
    """两段式数据库初始化：先异步验证连通性，再子进程执行迁移。"""
    # ── 第一阶段：纯异步连通性验证 ──
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("✅ 数据库连接验证通过")
    except Exception as e:
        logger.info(
            f"❌ 数据库连接异常: {e}",
        )
        raise RuntimeError("DB connection failed: " + str(e)) from e

    # ── 第二阶段：子进程执行 Alembic 迁移 ──
    logger.info("🔄 开始执行数据库初始化...")
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "alembic",
        "upgrade",
        "head",
    )
    try:
        await asyncio.wait_for(proc.wait(), timeout=60.0)
    except TimeoutError:
        proc.kill()
        await proc.wait()
        logger.error("❌ 迁移执行超时(>60s)，请检查是否有锁表或超大 DDL")
        raise RuntimeError("Migration timed out") from None

    if proc.returncode != 0:
        logger.error(f"❌ 迁移脚本执行失败 (exit={proc.returncode})")
        raise RuntimeError(f"Migration failed with code {proc.returncode}")

    logger.info("✅ 数据库初始化完成")


async def close_db() -> None:
    await engine.dispose()


async def get_session() -> AsyncGenerator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


@event.listens_for(Session, "before_flush")
def _populate_audit_fields(session: Session, _flush_context, _instances) -> None:
    """在数据库flush之前自动填充字段

    Args:
        session (Session): SQLAlchemy会话对象
        _flush_context (_type_): flush上下文
        _instances (_type_): 相关实例
    """
    now = datetime.now()

    # 新建对象，设置create_time和update_time
    for obj in session.new:
        if hasattr(obj, "create_time") and getattr(obj, "create_time") is None:
            setattr(obj, "create_time", now)
        if hasattr(obj, "update_time") and getattr(obj, "update_time") is None:
            setattr(obj, "update_time", now)

    # 更新对象，设置update_time
    for obj in session.dirty:
        if obj in session.new:
            continue
        if hasattr(obj, "update_time"):
            setattr(obj, "update_time", now)
