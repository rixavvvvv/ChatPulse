"""
Agent Presence Service

Tracks online/offline/away status of agents via heartbeats.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import AgentPresence, AgentPresenceStatus

logger = logging.getLogger(__name__)

# Agents are considered offline after this timeout without heartbeat
HEARTBEAT_TIMEOUT_SECONDS = 120


async def update_heartbeat(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
    status: AgentPresenceStatus = AgentPresenceStatus.online,
    metadata_json: dict | None = None,
) -> AgentPresence:
    """Update agent heartbeat — upsert."""
    stmt = select(AgentPresence).where(
        and_(
            AgentPresence.user_id == user_id,
            AgentPresence.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    presence = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if presence:
        presence.status = status
        presence.last_heartbeat_at = now
        if metadata_json is not None:
            presence.metadata_json = metadata_json
        presence.updated_at = now
    else:
        presence = AgentPresence(
            user_id=user_id,
            workspace_id=workspace_id,
            status=status,
            last_heartbeat_at=now,
            metadata_json=metadata_json or {},
        )
        db.add(presence)

    await db.commit()
    await db.refresh(presence)
    return presence


async def set_offline(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
) -> None:
    """Explicitly set agent as offline (e.g., on WebSocket disconnect)."""
    stmt = select(AgentPresence).where(
        and_(
            AgentPresence.user_id == user_id,
            AgentPresence.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    presence = result.scalar_one_or_none()

    if presence:
        presence.status = AgentPresenceStatus.offline
        presence.updated_at = datetime.now(timezone.utc)
        await db.commit()


async def get_online_agents(
    db: AsyncSession,
    workspace_id: int,
) -> list[AgentPresence]:
    """Get all agents currently online (heartbeat within timeout)."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)

    stmt = (
        select(AgentPresence)
        .where(
            and_(
                AgentPresence.workspace_id == workspace_id,
                AgentPresence.status != AgentPresenceStatus.offline,
                AgentPresence.last_heartbeat_at >= cutoff,
            )
        )
        .order_by(AgentPresence.last_heartbeat_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_all_agents_status(
    db: AsyncSession,
    workspace_id: int,
) -> list[AgentPresence]:
    """Get presence status for all agents in workspace."""
    stmt = (
        select(AgentPresence)
        .where(AgentPresence.workspace_id == workspace_id)
        .order_by(AgentPresence.status, AgentPresence.last_heartbeat_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def expire_stale_agents(
    db: AsyncSession,
) -> int:
    """Mark agents as offline if heartbeat has expired. Run periodically."""
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=HEARTBEAT_TIMEOUT_SECONDS)

    result = await db.execute(
        update(AgentPresence)
        .where(
            and_(
                AgentPresence.status != AgentPresenceStatus.offline,
                AgentPresence.last_heartbeat_at < cutoff,
            )
        )
        .values(status=AgentPresenceStatus.offline)
    )
    await db.commit()
    return result.rowcount
