"""
Conversation Unread Service

Tracks per-agent unread state for conversations.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationUnreadState

logger = logging.getLogger(__name__)


async def mark_conversation_read(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
    workspace_id: int,
    last_read_message_id: int | None = None,
) -> ConversationUnreadState:
    """Mark a conversation as fully read by a user."""
    stmt = select(ConversationUnreadState).where(
        and_(
            ConversationUnreadState.conversation_id == conversation_id,
            ConversationUnreadState.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    state = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)

    if not state:
        state = ConversationUnreadState(
            conversation_id=conversation_id,
            workspace_id=workspace_id,
            user_id=user_id,
            unread_count=0,
            last_read_message_id=last_read_message_id,
            last_read_at=now,
        )
        db.add(state)
    else:
        state.unread_count = 0
        state.last_read_at = now
        if last_read_message_id:
            state.last_read_message_id = last_read_message_id
        state.updated_at = now

    await db.commit()
    await db.refresh(state)
    return state


async def get_unread_count(
    db: AsyncSession,
    conversation_id: int,
    user_id: int,
) -> int:
    stmt = select(ConversationUnreadState.unread_count).where(
        and_(
            ConversationUnreadState.conversation_id == conversation_id,
            ConversationUnreadState.user_id == user_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def get_total_unread(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
) -> int:
    """Get total unread count across all conversations for a user."""
    stmt = select(func.sum(ConversationUnreadState.unread_count)).where(
        and_(
            ConversationUnreadState.user_id == user_id,
            ConversationUnreadState.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def get_unread_conversations(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
) -> list[ConversationUnreadState]:
    """Get all conversations with unread messages for a user."""
    stmt = (
        select(ConversationUnreadState)
        .where(
            and_(
                ConversationUnreadState.user_id == user_id,
                ConversationUnreadState.workspace_id == workspace_id,
                ConversationUnreadState.unread_count > 0,
            )
        )
        .order_by(ConversationUnreadState.updated_at.desc())
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def ensure_unread_state(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    user_id: int,
) -> ConversationUnreadState:
    """Create unread state if it doesn't exist."""
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
    await db.commit()
    await db.refresh(state)
    return state


async def batch_mark_read(
    db: AsyncSession,
    user_id: int,
    workspace_id: int,
    conversation_ids: list[int],
) -> int:
    """Mark multiple conversations as read at once."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        update(ConversationUnreadState)
        .where(
            and_(
                ConversationUnreadState.user_id == user_id,
                ConversationUnreadState.workspace_id == workspace_id,
                ConversationUnreadState.conversation_id.in_(conversation_ids),
            )
        )
        .values(unread_count=0, last_read_at=now)
    )
    await db.commit()
    return result.rowcount
