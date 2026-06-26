from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import col, select

from app.models.user import User


async def get_user_by_username(session: AsyncSession, username: str) -> User | None:
    result = await session.execute(select(User).where(col(User.username) == username))
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, user: User) -> User:
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
