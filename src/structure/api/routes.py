from fastapi import APIRouter

from structure.api.endpoints import health, structure

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(structure.router, prefix="/v1/video")
