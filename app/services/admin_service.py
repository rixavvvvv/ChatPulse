from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.usage_tracking import UsageTracking
from app.models.workspace import Workspace


async def list_all_workspaces(session: AsyncSession) -> list[Workspace]:
    stmt = select(Workspace).order_by(Workspace.created_at.desc())
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def list_workspace_usage_messages_sent(
    session: AsyncSession,
) -> list[tuple[Workspace, UsageTracking]]:
    stmt = (
        select(Workspace, UsageTracking)
        .join(UsageTracking, UsageTracking.workspace_id == Workspace.id)
        .order_by(UsageTracking.billing_cycle.desc(), Workspace.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.all())
