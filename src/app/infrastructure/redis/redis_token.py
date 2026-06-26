from redis.asyncio import Redis

from app.core.settings import settings


class RedisTokenService:
    def __init__(self) -> None:
        self.client = Redis.from_url(settings.redis_url, decode_responses=True)

    async def store_token(self, user_id: int, token: str, expiration_seconds: int) -> None:
        await self.client.set(self._token_key(user_id), token, ex=expiration_seconds)

    async def get_token(self, user_id: int) -> str | None:
        return await self.client.get(self._token_key(user_id))

    async def validate_token(self, user_id: int, token: str) -> bool:
        stored = await self.get_token(user_id)
        return stored is not None and stored == token

    async def remove_token(self, user_id: int) -> None:
        await self.client.delete(self._token_key(user_id))

    @staticmethod
    def _token_key(user_id: int) -> str:
        return f"token:{user_id}"
