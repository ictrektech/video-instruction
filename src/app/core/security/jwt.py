from datetime import UTC, datetime, timedelta

from jose import JWTError, jwt

from app.core.settings import settings
from app.schemas.user import TokenPayload


def generate_token(user_id: int, username: str) -> str:
    payload = {
        "userId": user_id,
        "username": username,
        "iat": int(datetime.now(UTC).timestamp()),
        "exp": int(
            (datetime.now(UTC) + timedelta(seconds=settings.jwt_expiration_seconds)).timestamp()
        ),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_token(token: str) -> TokenPayload | None:
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
        return TokenPayload.model_validate(payload)
    except JWTError:
        return None
