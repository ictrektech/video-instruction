from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors.error_codes import BusinessErrorCode
from app.core.errors.exceptions import ApiException
from app.core.security.jwt import generate_token
from app.core.security.password import hash_password, verify_password
from app.core.settings import settings
from app.crud.user import create_user, get_user_by_username
from app.infrastructure.redis.redis_token import RedisTokenService
from app.models.user import User
from app.schemas.user import AddUserCommand, LoginCommand, LoginDTO, UserDTO


async def login(session: AsyncSession, cmd: LoginCommand) -> LoginDTO:
    user = await get_user_by_username(session, cmd.username)
    if not user:
        raise ApiException(BusinessErrorCode.COMMON_OBJECT_NOT_FOUND, "用户", "用户名或密码错误")

    if not verify_password(cmd.password, user.password):
        raise ApiException(BusinessErrorCode.COMMON_OBJECT_NOT_FOUND, "用户", "用户名或密码错误")

    if user.status != 1:
        raise ApiException(BusinessErrorCode.COMMON_UNSUPPORTED_OPERATION)

    if user.id is None:
        raise ApiException(BusinessErrorCode.ADD_USER_FAILED)

    token = generate_token(user.id, user.username)
    redis_service = RedisTokenService()
    await redis_service.store_token(user.id, token, settings.jwt_expiration_seconds)

    return LoginDTO(
        token=token,
        userId=user.id,
        username=user.username,
        realName=user.real_name,
    )


async def add_user(session: AsyncSession, cmd: AddUserCommand) -> UserDTO:
    existing = await get_user_by_username(session, cmd.username)
    if existing:
        raise ApiException(BusinessErrorCode.USERNAME_EXISTS)

    user = User(
        username=cmd.username,
        password=hash_password(cmd.password),
        status=1,
    )
    user = await create_user(session, user)
    if user.id is None:
        raise ApiException(BusinessErrorCode.ADD_USER_FAILED)
    return UserDTO(
        id=user.id,
        username=user.username,
    )
