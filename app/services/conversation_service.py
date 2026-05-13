"""
Conversation Service

Core CRUD and business logic for conversations.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.conversation import (
    Conversation,
    ConversationChannel,
    ConversationPriority,
    ConversationStatus,
    ConversationUnreadState,
)

logger = logging.getLogger(__name__)


async def get_conversation_by_id(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
) -> Conversation | None:
    stmt = select(Conversation).where(
        and_(
            Conversation.id == conversation_id,
            Conversation.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_or_create_conversation(
    db: AsyncSession,
    workspace_id: int,
    contact_id: int,
    channel: ConversationChannel = ConversationChannel.whatsapp,
) -> tuple[Conversation, bool]:
    """
    Get an existing open/assigned conversation or create a new one.

    Returns (conversation, created) tuple.
    """
    # Look for existing open or assigned conversation
    stmt = select(Conversation).where(
        and_(
            Conversation.workspace_id == workspace_id,
            Conversation.contact_id == contact_id,
            Conversation.channel == channel,
            Conversation.status.in_([
                ConversationStatus.open,
                ConversationStatus.assigned,
            ]),
        )
    ).order_by(Conversation.updated_at.desc()).limit(1)

    result = await db.execute(stmt)
    existing = result.scalar_one_or_none()

    if existing:
        return existing, False

    # Create new conversation
    conversation = Conversation(
        workspace_id=workspace_id,
        contact_id=contact_id,
        channel=channel,
        status=ConversationStatus.open,
        priority=ConversationPriority.normal,
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)

    return conversation, True


async def create_conversation(
    db: AsyncSession,
    workspace_id: int,
    contact_id: int,
    channel: ConversationChannel = ConversationChannel.whatsapp,
    priority: ConversationPriority = ConversationPriority.normal,
    subject: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> Conversation:
    conversation = Conversation(
        workspace_id=workspace_id,
        contact_id=contact_id,
        channel=channel,
        status=ConversationStatus.open,
        priority=priority,
        subject=subject,
        metadata_json=metadata_json or {},
    )
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def list_conversations(
    db: AsyncSession,
    workspace_id: int,
    status: ConversationStatus | None = None,
    channel: ConversationChannel | None = None,
    priority: ConversationPriority | None = None,
    assigned_to: int | None = None,
    label_id: int | None = None,
    search: str | None = None,
    limit: int = 50,
    offset: int = 0,
    user_id: int | None = None,
) -> tuple[list[dict[str, Any]], int]:
    """
    List conversations with optional filters.
    Returns conversations enriched with unread_count for the requesting user.
    """
    query = select(Conversation).where(Conversation.workspace_id == workspace_id)

    if status:
        query = query.where(Conversation.status == status)
    if channel:
        query = query.where(Conversation.channel == channel)
    if priority:
        query = query.where(Conversation.priority == priority)
    if search:
        query = query.where(Conversation.subject.ilike(f"%{search}%"))

    if assigned_to:
        from app.models.conversation import ConversationAssignment
        query = query.join(
            ConversationAssignment,
            and_(
                ConversationAssignment.conversation_id == Conversation.id,
                ConversationAssignment.agent_user_id == assigned_to,
                ConversationAssignment.is_active == True,
            ),
        )

    if label_id:
        from app.models.conversation import ConversationLabelAssignment
        query = query.join(
            ConversationLabelAssignment,
            and_(
                ConversationLabelAssignment.conversation_id == Conversation.id,
                ConversationLabelAssignment.label_id == label_id,
            ),
        )

    # Count
    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    # Paginate
    query = query.order_by(
        Conversation.last_message_at.desc().nulls_last(),
        Conversation.updated_at.desc(),
    ).offset(offset).limit(limit)

    result = await db.execute(query)
    conversations = list(result.scalars().all())

    # Enrich with unread counts
    enriched = []
    for conv in conversations:
        unread_count = 0
        if user_id:
            unread_stmt = select(ConversationUnreadState.unread_count).where(
                and_(
                    ConversationUnreadState.conversation_id == conv.id,
                    ConversationUnreadState.user_id == user_id,
                )
            )
            unread_result = await db.execute(unread_stmt)
            unread_count = unread_result.scalar() or 0

        enriched.append({
            "conversation": conv,
            "unread_count": unread_count,
        })

    return enriched, total


async def update_conversation(
    db: AsyncSession,
    conversation: Conversation,
    priority: ConversationPriority | None = None,
    subject: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> Conversation:
    if priority is not None:
        conversation.priority = priority
    if subject is not None:
        conversation.subject = subject
    if metadata_json is not None:
        conversation.metadata_json = metadata_json

    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(conversation)
    return conversation


async def update_last_message(
    db: AsyncSession,
    conversation: Conversation,
    preview: str,
    message_at: datetime,
) -> None:
    """Update conversation's last message preview and timestamp."""
    conversation.last_message_preview = preview[:512] if preview else None
    conversation.last_message_at = message_at
    conversation.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def get_conversation_counts(
    db: AsyncSession,
    workspace_id: int,
) -> dict[str, int]:
    """Get counts of conversations by status."""
    results = {}
    for status in ConversationStatus:
        stmt = select(func.count()).where(
            and_(
                Conversation.workspace_id == workspace_id,
                Conversation.status == status,
            )
        )
        result = await db.execute(stmt)
        results[status.value] = result.scalar() or 0

    results["total"] = sum(results.values())
    return results
