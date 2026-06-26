from fastapi import APIRouter

from app.api.endpoints import health, user

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(user.router, prefix="/user", tags=["user"])
