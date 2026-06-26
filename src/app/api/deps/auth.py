from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.core.errors.error_codes import BusinessErrorCode
from app.core.errors.exceptions import ApiException
from app.core.request_context import set_request_user
from app.core.security.jwt import decode_token
from app.db.session import get_session
from app.infrastructure.redis.redis_token import RedisTokenService
from app.models.user import User
from app.schemas.user import CurrentUser

security_scheme = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security_scheme),
    session: AsyncSession = Depends(get_session),
) -> CurrentUser:
    token = credentials.credentials
    payload = decode_token(token)
    if not payload:
        raise ApiException(BusinessErrorCode.USER_NOT_FOUND)

    user_id = payload.userId
    username = payload.username

    redis_service = RedisTokenService()
    is_valid = await redis_service.validate_token(int(user_id), token)
    if not is_valid:
        raise ApiException(BusinessErrorCode.USER_NOT_FOUND, username)

    result = await session.execute(select(User).where(col(User.id) == int(user_id)))
    user = result.scalar_one_or_none()
    if not user:
        raise ApiException(BusinessErrorCode.USER_NOT_FOUND, username)
    if user.id is None:
        raise ApiException(BusinessErrorCode.USER_NOT_FOUND, username)

    set_request_user(user.id, user.username)
    return CurrentUser(id=user.id, username=user.username)
