from fastapi import APIRouter

from structure.api.endpoints import (
    description,
    description_jobs,
    health,
    storage,
    structure,
    structure_jobs,
)

router = APIRouter(prefix="/api")
router.include_router(health.router)
router.include_router(structure.router, prefix="/v1/video")
router.include_router(storage.router, prefix="/v1/video")
router.include_router(description.router, prefix="/v1/video")
router.include_router(structure_jobs.router, prefix="/v2/video")
router.include_router(description_jobs.router, prefix="/v2/video")
