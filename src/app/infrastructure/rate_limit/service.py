from fastapi import Request
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.core.request_context import get_request_user_id


def _rate_limit_key(request: Request) -> str:
    user_id = get_request_user_id()
    if user_id is not None:
        return f"user:{user_id}"
    return get_remote_address(request)


limiter = Limiter(key_func=_rate_limit_key)


def get_limiter() -> Limiter:
    return limiter
