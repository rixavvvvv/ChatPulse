from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_tracking import UsageTracking


def get_current_billing_cycle(now: datetime | None = None) -> str:
    target = now or datetime.now(tz=UTC)
    return f"{target.year:04d}-{target.month:02d}"


async def increment_messages_sent(
    session: AsyncSession,
    *,
    workspace_id: int,
    increment_by: int = 1,
    billing_cycle: str | None = None,
) -> UsageTracking:
    cycle = billing_cycle or get_current_billing_cycle()

    stmt = select(UsageTracking).where(
        UsageTracking.workspace_id == workspace_id,
        UsageTracking.billing_cycle == cycle,
    )
    usage = (await session.execute(stmt)).scalar_one_or_none()

    if usage is None:
        usage = UsageTracking(
            workspace_id=workspace_id,
            billing_cycle=cycle,
            messages_sent=max(0, increment_by),
        )
        session.add(usage)
        await session.flush()
        return usage

    usage.messages_sent = max(0, usage.messages_sent + increment_by)
    await session.flush()
    return usage
