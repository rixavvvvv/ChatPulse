from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.user_subscription import UserSubscription, UserSubscriptionStatus


async def get_plan_by_name(session: AsyncSession, name: str) -> Plan | None:
    stmt = select(Plan).where(Plan.name == name)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_plan_by_id(session: AsyncSession, plan_id: int) -> Plan | None:
    return await session.get(Plan, plan_id)


async def list_plans(session: AsyncSession) -> list[Plan]:
    stmt = select(Plan).order_by(Plan.price.asc(), Plan.id.asc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def create_plan(
    session: AsyncSession,
    *,
    name: str,
    message_limit: int,
    price: float,
) -> Plan:
    plan = Plan(
        name=name,
        message_limit=message_limit,
        price=price,
    )
    session.add(plan)
    await session.commit()
    await session.refresh(plan)
    return plan


async def upsert_user_subscription(
    session: AsyncSession,
    *,
    user_id: int,
    plan_id: int,
    status: UserSubscriptionStatus = UserSubscriptionStatus.active,
) -> UserSubscription:
    stmt = select(UserSubscription).where(UserSubscription.user_id == user_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing is None:
        existing = UserSubscription(
            user_id=user_id,
            plan_id=plan_id,
            status=status,
        )
        session.add(existing)
    else:
        existing.plan_id = plan_id
        existing.status = status

    await session.commit()
    await session.refresh(existing)
    return existing


async def get_user_subscription(
    session: AsyncSession,
    *,
    user_id: int,
) -> UserSubscription | None:
    stmt = select(UserSubscription).where(UserSubscription.user_id == user_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()
