from fastapi import APIRouter

from app.schemas.common.response import ResponseDTO

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseDTO[dict])
async def health_check() -> ResponseDTO[dict]:
    """健康检查端点，用于容器编排系统的存活探针。"""
    return ResponseDTO.ok(
        {
            "status": "ok",
        }
    )
