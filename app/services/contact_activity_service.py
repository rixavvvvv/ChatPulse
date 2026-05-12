from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_intelligence import ContactActivity


async def record_contact_activity(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    actor_user_id: int | None,
    type: str,
    payload: dict | None = None,
) -> ContactActivity:
    row = ContactActivity(
        workspace_id=workspace_id,
        contact_id=contact_id,
        actor_user_id=actor_user_id,
        type=type,
        payload=payload or {},
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_contact_activities(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    limit: int = 50,
) -> list[ContactActivity]:
    cap = max(1, min(limit, 200))
    stmt = (
        select(ContactActivity)
        .where(
            ContactActivity.workspace_id == workspace_id,
            ContactActivity.contact_id == contact_id,
        )
        .order_by(ContactActivity.created_at.desc())
        .limit(cap)
    )
    return list((await session.execute(stmt)).scalars().all())

