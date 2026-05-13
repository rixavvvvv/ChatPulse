"""
Conversation Assignment Service

Manages agent assignments to conversations with history tracking.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    Conversation,
    ConversationAssignment,
    ConversationStatus,
    ConversationUnreadState,
)
from app.services.conversation_state_engine import (
    InvalidTransitionError,
    StaleVersionError,
    transition_state,
)

logger = logging.getLogger(__name__)


async def assign_agent(
    db: AsyncSession,
    conversation: Conversation,
    agent_user_id: int,
    assigned_by: int,
    expected_version: int,
) -> ConversationAssignment:
    """
    Assign an agent to a conversation.

    1. Validate optimistic lock
    2. Unassign any currently active agent
    3. Create new assignment
    4. Transition conversation to 'assigned' status
    5. Create unread state for the agent
    """
    # Unassign current agent if any
    await _unassign_current(db, conversation.id, conversation.workspace_id)

    # Create new assignment
    assignment = ConversationAssignment(
        conversation_id=conversation.id,
        workspace_id=conversation.workspace_id,
        agent_user_id=agent_user_id,
        assigned_by=assigned_by,
        is_active=True,
    )
    db.add(assignment)

    # Transition to assigned
    try:
        await transition_state(
            db, conversation,
            ConversationStatus.assigned,
            expected_version,
            actor_user_id=assigned_by,
        )
    except InvalidTransitionError:
        # If already assigned, just update the version
        conversation.version += 1
        conversation.updated_at = datetime.now(timezone.utc)
        await db.commit()

    # Ensure agent has an unread state for this conversation
    await _ensure_unread_state(db, conversation.id, conversation.workspace_id, agent_user_id)

    await db.commit()
    await db.refresh(assignment)
    return assignment


async def unassign_agent(
    db: AsyncSession,
    conversation: Conversation,
    expected_version: int,
    actor_user_id: int,
) -> None:
    """Unassign all agents and transition back to open."""
    await _unassign_current(db, conversation.id, conversation.workspace_id)

    await transition_state(
        db, conversation,
        ConversationStatus.open,
        expected_version,
        actor_user_id=actor_user_id,
    )


async def get_active_assignment(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
) -> ConversationAssignment | None:
    stmt = select(ConversationAssignment).where(
        and_(
            ConversationAssignment.conversation_id == conversation_id,
            ConversationAssignment.workspace_id == workspace_id,
            ConversationAssignment.is_active == True,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_assignment_history(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    limit: int = 20,
) -> list[ConversationAssignment]:
    stmt = (
        select(ConversationAssignment)
        .where(
            and_(
                ConversationAssignment.conversation_id == conversation_id,
                ConversationAssignment.workspace_id == workspace_id,
            )
        )
        .order_by(ConversationAssignment.assigned_at.desc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_agent_active_count(
    db: AsyncSession,
    agent_user_id: int,
    workspace_id: int,
) -> int:
    """Count active conversations assigned to an agent."""
    stmt = select(func.count()).where(
        and_(
            ConversationAssignment.agent_user_id == agent_user_id,
            ConversationAssignment.workspace_id == workspace_id,
            ConversationAssignment.is_active == True,
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def round_robin_assign(
    db: AsyncSession,
    conversation: Conversation,
    workspace_id: int,
    expected_version: int,
    eligible_user_ids: list[int],
    assigned_by: int,
) -> ConversationAssignment | None:
    """
    Assign to the agent with the fewest active conversations.
    """
    if not eligible_user_ids:
        return None

    best_agent_id = eligible_user_ids[0]
    lowest_count = float("inf")

    for user_id in eligible_user_ids:
        count = await get_agent_active_count(db, user_id, workspace_id)
        if count < lowest_count:
            lowest_count = count
            best_agent_id = user_id

    return await assign_agent(
        db, conversation, best_agent_id, assigned_by, expected_version
    )


async def _unassign_current(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
) -> None:
    """Unassign any currently active assignment."""
    stmt = select(ConversationAssignment).where(
        and_(
            ConversationAssignment.conversation_id == conversation_id,
            ConversationAssignment.workspace_id == workspace_id,
            ConversationAssignment.is_active == True,
        )
    )
    result = await db.execute(stmt)
    current = result.scalar_one_or_none()

    if current:
        current.is_active = False
        current.unassigned_at = datetime.now(timezone.utc)


async def _ensure_unread_state(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    user_id: int,
) -> ConversationUnreadState:
    """Ensure an unread state record exists for this user+conversation."""
    stmt = select(ConversationUnreadState).where(
        and_(
            ConversationUnreadState.conversation_id == conversation_id,
            ConversationUnreadState.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing

    state = ConversationUnreadState(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        user_id=user_id,
        unread_count=0,
    )
    db.add(state)
    return state
