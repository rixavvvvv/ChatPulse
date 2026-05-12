from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User, UserRole


def normalize_email(email: str) -> str:
    return email.strip().lower()


async def get_user_by_email(session: AsyncSession, email: str) -> User | None:
    normalized = normalize_email(email)
    stmt = select(User).where(func.lower(User.email) == normalized)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_user_by_id(session: AsyncSession, user_id: int) -> User | None:
    return await session.get(User, user_id)


async def list_users(session: AsyncSession) -> list[User]:
    stmt = select(User).order_by(User.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_user(
    session: AsyncSession,
    email: str,
    password_hash: str,
    role: UserRole = UserRole.user,
    subscription_plan: str = "free",
    is_active: bool = True,
) -> User:
    user = User(
        email=normalize_email(email),
        password_hash=password_hash,
        role=role.value,
        subscription_plan=subscription_plan,
        is_active=is_active,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_subscription_plan(
    session: AsyncSession,
    user: User,
    subscription_plan: str,
) -> User:
    user.subscription_plan = subscription_plan
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_active_status(
    session: AsyncSession,
    user: User,
    is_active: bool,
) -> User:
    user.is_active = is_active
    await session.commit()
    await session.refresh(user)
    return user


async def update_user_role(
    session: AsyncSession,
    user: User,
    role: UserRole,
) -> User:
    user.role = role.value
    await session.commit()
    await session.refresh(user)
    return user
