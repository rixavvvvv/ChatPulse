from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import delete, func, insert, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.contact_intelligence import Segment, SegmentMembership
from app.services.segment_filter_dsl import compile_to_where_clause


async def create_segment(
    session: AsyncSession,
    *,
    workspace_id: int,
    name: str,
    definition: dict[str, Any],
) -> Segment:
    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Segment name is required")
    compiled = compile_to_where_clause(workspace_id=workspace_id, definition=definition)
    _ = compiled
    row = Segment(workspace_id=workspace_id, name=normalized_name, definition=definition)
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_segments(session: AsyncSession, *, workspace_id: int) -> list[Segment]:
    stmt = select(Segment).where(Segment.workspace_id == workspace_id).order_by(Segment.id.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_segment(session: AsyncSession, *, workspace_id: int, segment_id: int) -> Segment | None:
    stmt = select(Segment).where(Segment.workspace_id == workspace_id, Segment.id == segment_id)
    return (await session.execute(stmt)).scalar_one_or_none()


async def update_segment(
    session: AsyncSession,
    *,
    workspace_id: int,
    segment_id: int,
    name: str | None = None,
    definition: dict[str, Any] | None = None,
) -> Segment:
    segment = await get_segment(session=session, workspace_id=workspace_id, segment_id=segment_id)
    if not segment:
        raise ValueError("Segment not found")

    if name is not None:
        normalized_name = name.strip()
        if not normalized_name:
            raise ValueError("Segment name is required")
        segment.name = normalized_name

    if definition is not None:
        # Validate the definition compiles
        compiled = compile_to_where_clause(workspace_id=workspace_id, definition=definition)
        _ = compiled
        segment.definition = definition

    await session.commit()
    await session.refresh(segment)
    return segment


async def preview_segment_count(
    session: AsyncSession,
    *,
    workspace_id: int,
    definition: dict[str, Any],
) -> int:
    compiled = compile_to_where_clause(workspace_id=workspace_id, definition=definition)
    stmt = select(func.count(Contact.id)).where(Contact.workspace_id == workspace_id, compiled.where_clause)
    return int((await session.execute(stmt)).scalar_one())


async def materialize_segment_membership(
    session: AsyncSession,
    *,
    workspace_id: int,
    segment: Segment,
) -> int:
    compiled = compile_to_where_clause(workspace_id=workspace_id, definition=segment.definition)

    await session.execute(
        delete(SegmentMembership).where(
            SegmentMembership.workspace_id == workspace_id,
            SegmentMembership.segment_id == segment.id,
        )
    )

    contacts_stmt = select(Contact.id).where(
        Contact.workspace_id == workspace_id,
        compiled.where_clause,
    )
    contact_ids = list((await session.execute(contacts_stmt)).scalars().all())
    if not contact_ids:
        segment.approx_size = 0
        segment.last_materialized_at = datetime.now(tz=UTC)
        await session.commit()
        return 0

    rows = [
        {"workspace_id": workspace_id, "segment_id": segment.id, "contact_id": cid}
        for cid in contact_ids
    ]
    await session.execute(insert(SegmentMembership), rows)
    segment.approx_size = len(contact_ids)
    segment.last_materialized_at = datetime.now(tz=UTC)
    await session.commit()
    return len(contact_ids)

