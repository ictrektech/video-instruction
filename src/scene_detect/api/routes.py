from fastapi import APIRouter

from scene_detect.api.endpoints import detect, detect_jobs, health

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(detect.router, prefix="/v1/scenes")
router.include_router(detect_jobs.router, prefix="/v2/scenes")
