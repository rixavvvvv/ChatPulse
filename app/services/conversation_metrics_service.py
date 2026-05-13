"""
Conversation Metrics Service

Real-time metrics and observability for the conversation system.
"""

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    AgentPresence,
    AgentPresenceStatus,
    Conversation,
    ConversationAssignment,
    ConversationMessage,
    ConversationStatus,
    ConversationUnreadState,
    MessageDirection,
)

logger = logging.getLogger(__name__)


async def get_conversation_metrics(
    db: AsyncSession,
    workspace_id: int,
) -> dict:
    """Get aggregate conversation metrics for a workspace."""
    # Status counts
    status_counts = {}
    for status in ConversationStatus:
        stmt = select(func.count()).where(
            and_(
                Conversation.workspace_id == workspace_id,
                Conversation.status == status,
            )
        )
        result = await db.execute(stmt)
        status_counts[status.value] = result.scalar() or 0

    total = sum(status_counts.values())

    # Message counts
    msg_stmt = select(
        func.count().label("total"),
        func.count(case((ConversationMessage.direction == MessageDirection.inbound, 1))).label("inbound"),
        func.count(case((ConversationMessage.direction == MessageDirection.outbound, 1))).label("outbound"),
    ).where(ConversationMessage.workspace_id == workspace_id)

    msg_result = await db.execute(msg_stmt)
    msg_row = msg_result.one()

    # Average response time (time between last inbound and first outbound after it)
    avg_response = await _calculate_avg_response_time(db, workspace_id)

    # Average resolution time
    avg_resolution = await _calculate_avg_resolution_time(db, workspace_id)

    return {
        "total_conversations": total,
        "open_conversations": status_counts.get("open", 0),
        "assigned_conversations": status_counts.get("assigned", 0),
        "resolved_conversations": status_counts.get("resolved", 0),
        "closed_conversations": status_counts.get("closed", 0),
        "avg_response_time_seconds": avg_response,
        "avg_resolution_time_seconds": avg_resolution,
        "total_messages": msg_row.total,
        "inbound_messages": msg_row.inbound,
        "outbound_messages": msg_row.outbound,
    }


async def get_agent_workload(
    db: AsyncSession,
    workspace_id: int,
) -> list[dict]:
    """Get workload distribution across agents."""
    # Active assignments per agent
    stmt = (
        select(
            ConversationAssignment.agent_user_id,
            func.count().label("active_count"),
        )
        .where(
            and_(
                ConversationAssignment.workspace_id == workspace_id,
                ConversationAssignment.is_active == True,
            )
        )
        .group_by(ConversationAssignment.agent_user_id)
    )
    result = await db.execute(stmt)
    workloads = []

    for row in result:
        # Count resolved today
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        resolved_stmt = select(func.count()).where(
            and_(
                ConversationAssignment.agent_user_id == row.agent_user_id,
                ConversationAssignment.workspace_id == workspace_id,
                ConversationAssignment.is_active == False,
                ConversationAssignment.unassigned_at >= today_start,
            )
        )
        resolved_result = await db.execute(resolved_stmt)
        resolved_today = resolved_result.scalar() or 0

        workloads.append({
            "user_id": row.agent_user_id,
            "active_conversations": row.active_count,
            "resolved_today": resolved_today,
            "avg_response_time_seconds": None,
        })

    return workloads


async def get_realtime_stats(
    db: AsyncSession,
    workspace_id: int,
) -> dict:
    """Get real-time operational stats for dashboard."""
    # Online agents
    cutoff = datetime.now(timezone.utc) - timedelta(seconds=120)
    online_stmt = select(func.count()).where(
        and_(
            AgentPresence.workspace_id == workspace_id,
            AgentPresence.status != AgentPresenceStatus.offline,
            AgentPresence.last_heartbeat_at >= cutoff,
        )
    )
    online_result = await db.execute(online_stmt)
    online_agents = online_result.scalar() or 0

    # Waiting conversations (open, not assigned)
    waiting_stmt = select(func.count()).where(
        and_(
            Conversation.workspace_id == workspace_id,
            Conversation.status == ConversationStatus.open,
        )
    )
    waiting_result = await db.execute(waiting_stmt)
    waiting = waiting_result.scalar() or 0

    # Total unread across all agents
    unread_stmt = select(func.sum(ConversationUnreadState.unread_count)).where(
        ConversationUnreadState.workspace_id == workspace_id,
    )
    unread_result = await db.execute(unread_stmt)
    total_unread = unread_result.scalar() or 0

    # Messages in last hour
    one_hour_ago = datetime.now(timezone.utc) - timedelta(hours=1)
    recent_msg_stmt = select(func.count()).where(
        and_(
            ConversationMessage.workspace_id == workspace_id,
            ConversationMessage.created_at >= one_hour_ago,
        )
    )
    recent_result = await db.execute(recent_msg_stmt)
    messages_last_hour = recent_result.scalar() or 0

    return {
        "online_agents": online_agents,
        "waiting_conversations": waiting,
        "total_unread": total_unread,
        "messages_last_hour": messages_last_hour,
    }


async def _calculate_avg_response_time(
    db: AsyncSession,
    workspace_id: int,
    days: int = 7,
) -> float | None:
    """
    Calculate average first-response time.
    Approximation: (first outbound time - conversation created_at) for conversations
    created in the last N days.
    """
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    # Get conversations with at least one outbound message
    stmt = (
        select(
            Conversation.id,
            Conversation.created_at.label("conv_created"),
            func.min(ConversationMessage.created_at).label("first_reply"),
        )
        .join(
            ConversationMessage,
            and_(
                ConversationMessage.conversation_id == Conversation.id,
                ConversationMessage.direction == MessageDirection.outbound,
            ),
        )
        .where(
            and_(
                Conversation.workspace_id == workspace_id,
                Conversation.created_at >= cutoff,
            )
        )
        .group_by(Conversation.id, Conversation.created_at)
    )

    result = await db.execute(stmt)
    rows = result.all()

    if not rows:
        return None

    total_seconds = 0
    count = 0
    for row in rows:
        diff = (row.first_reply - row.conv_created).total_seconds()
        if diff > 0:
            total_seconds += diff
            count += 1

    return total_seconds / count if count > 0 else None


async def _calculate_avg_resolution_time(
    db: AsyncSession,
    workspace_id: int,
    days: int = 30,
) -> float | None:
    """Calculate average time from creation to resolution."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    stmt = select(
        func.avg(
            func.extract("epoch", Conversation.resolved_at - Conversation.created_at)
        )
    ).where(
        and_(
            Conversation.workspace_id == workspace_id,
            Conversation.resolved_at.is_not(None),
            Conversation.created_at >= cutoff,
        )
    )

    result = await db.execute(stmt)
    avg = result.scalar()
    return float(avg) if avg else None
