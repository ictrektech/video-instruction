from logging import getLogger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import api_router
from app.core.settings import settings
from app.middlewares import (
    add_exception_handlers,
    add_request_context_middleware,
)

logger = getLogger(__name__)


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
    )

    add_exception_handlers(application)
    add_request_context_middleware(application)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(api_router, prefix="/api")

    return application


app = create_application()
