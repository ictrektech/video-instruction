from contextlib import asynccontextmanager
from logging import getLogger

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from shared.middlewares import add_exception_handlers, add_request_context_middleware
from shared.task_status import init_task_db
from structure.api.routes import router as structure_router
from structure.core.settings import settings

logger = getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI):
    init_task_db("structure")
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

    application.include_router(structure_router)

    return application


app = create_application()
