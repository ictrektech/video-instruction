from fastapi import APIRouter

from scene_detect.api.endpoints import detect, health

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(detect.router, prefix="/v1/scenes")
