from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.domain_event import DomainEvent


async def insert_domain_events_for_ingestion(
    session: AsyncSession,
    *,
    webhook_ingestion_id: int,
    events: list[tuple[str, int | None, dict[str, Any], str | None]],
) -> int:
    """Insert normalized events. Each tuple is (event_type, workspace_id, payload, dedupe_key).

    Skips rows when dedupe_key is provided and already exists for this ingestion.
    """
    inserted = 0
    for event_type, workspace_id, payload, dedupe_key in events:
        if dedupe_key:
            existing = await session.execute(
                select(DomainEvent.id).where(
                    DomainEvent.webhook_ingestion_id == webhook_ingestion_id,
                    DomainEvent.dedupe_key == dedupe_key,
                )
            )
            if existing.scalar_one_or_none() is not None:
                continue
        session.add(
            DomainEvent(
                event_type=event_type,
                workspace_id=workspace_id,
                webhook_ingestion_id=webhook_ingestion_id,
                dedupe_key=dedupe_key,
                payload=payload,
            )
        )
        inserted += 1
    return inserted
