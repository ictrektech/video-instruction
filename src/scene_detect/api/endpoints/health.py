from fastapi import APIRouter

from shared.schemas.common.response import ResponseDTO

router = APIRouter(tags=["health"])


@router.get("/health", response_model=ResponseDTO[dict])
async def health_check() -> ResponseDTO[dict]:
    """Health check endpoint for container orchestration liveness probes."""
    return ResponseDTO.ok({"status": "ok", "service": "scene-detection"})
