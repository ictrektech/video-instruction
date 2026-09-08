from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from scene_detect.api.routes import router as detection_router
from scene_detect.core.settings import settings
from shared.jobs import init_db
from shared.middlewares import add_exception_handlers, add_request_context_middleware
from shared.utils.docs_page import mount_docs

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_db()
    yield


def create_application() -> FastAPI:
    application = FastAPI(
        title=settings.app_title,
        version=settings.app_version,
        lifespan=lifespan,
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

    application.include_router(detection_router)
    mount_docs(application)

    return application


app = create_application()
