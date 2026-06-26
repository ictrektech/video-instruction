from fastapi import APIRouter, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.schemas.common.response import ResponseDTO

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseDTO[dict])
async def health_check(
    session: AsyncSession = Depends(get_session),
) -> ResponseDTO[dict]:
    """健康检查端点，用于容器编排系统的存活探针。"""
    db_ok = True
    try:
        await session.execute(text("SELECT 1"))
    except Exception:
        db_ok = False

    return ResponseDTO.ok(
        {
            "status": "ok",
            "db": "ok" if db_ok else "ng",
        }
    )
