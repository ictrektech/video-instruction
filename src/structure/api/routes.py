from fastapi import APIRouter

from structure.api.endpoints import (
    description_jobs,
    health,
    structure_jobs,
)

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(structure_jobs.router, prefix="/v2/video")
router.include_router(description_jobs.router, prefix="/v2/video")
