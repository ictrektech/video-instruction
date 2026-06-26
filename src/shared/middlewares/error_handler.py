import os
from logging import getLogger

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from shared.core.errors.error_codes import ErrorCode
from shared.core.errors.error_utils import exc_origin
from shared.core.errors.exceptions import ApiException
from shared.schemas.common.response import ResponseDTO

logger = getLogger(__name__)


def _request_context(request: Request) -> str:
    client = request.client.host if request.client else "-"
    return f"method={request.method} path={request.url.path} client={client}"


def add_exception_handlers(application: FastAPI) -> None:
    @application.exception_handler(ApiException)
    async def api_exception_handler(req: Request, exc: ApiException) -> JSONResponse:
        filename, lineno = exc_origin(exc)
        logger.warning(
            f"api_exception | code={exc.code} message={exc.message} | {_request_context(req)}",
            extra={
                "source_file": filename,
                "source_line": lineno,
            },
        )
        payload = ResponseDTO.fail(code=exc.code, msg=exc.message)
        return JSONResponse(status_code=200, content=payload.model_dump())

    @application.exception_handler(Exception)
    async def unhandled_exception_handler(req: Request, exc: Exception) -> JSONResponse:
        logger.exception(
            f"unhandled_exception | {_request_context(req)}",
        )
        msg = str(exc) if os.getenv("APP_ENV", "dev") == "dev" else ErrorCode.FAILED.message
        payload = ResponseDTO.fail(code=ErrorCode.FAILED.code, msg=msg)
        return JSONResponse(status_code=500, content=payload.model_dump())
