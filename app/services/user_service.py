from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    stmt = select(User).where(User.email == email)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def create_user(session: AsyncSession, email: str, password_hash: str) -> User:
    user = User(email=email, password_hash=password_hash)
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user
