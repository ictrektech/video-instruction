from fastapi import FastAPI

from app.infrastructure.rate_limit.service import get_limiter
from app.utils.rate_limit import RateLimitMiddleware


def add_rate_limit_middleware(application: FastAPI) -> None:
    limiter = get_limiter()
    application.state.limiter = limiter
    application.add_middleware(RateLimitMiddleware)  # type: ignore[arg-type]
