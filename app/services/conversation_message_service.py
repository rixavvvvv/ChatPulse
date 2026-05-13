"""
Conversation Message Service

Handles message creation, listing, and delivery tracking integration.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    Conversation,
    ConversationMessage,
    ConversationUnreadState,
    MessageContentType,
    MessageDirection,
    MessageSenderType,
)
from app.services import conversation_service

logger = logging.getLogger(__name__)


async def create_message(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    direction: MessageDirection,
    sender_type: MessageSenderType,
    sender_id: int | None,
    content: str,
    content_type: MessageContentType = MessageContentType.text,
    provider_message_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ConversationMessage:
    """
    Create a message and update conversation metadata.

    Side effects:
    - Updates conversation.last_message_preview and last_message_at
    - Increments unread_count for all agents except the sender
    - Auto-reopens resolved/closed conversations on inbound messages
    """
    message = ConversationMessage(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        direction=direction,
        sender_type=sender_type,
        sender_id=sender_id,
        content_type=content_type,
        content=content,
        provider_message_id=provider_message_id,
        metadata_json=metadata_json or {},
    )
    db.add(message)
    await db.flush()  # Get the message ID

    # Update conversation last message
    conversation = await conversation_service.get_conversation_by_id(
        db, conversation_id, workspace_id
    )
    if conversation:
        await conversation_service.update_last_message(
            db, conversation,
            preview=content,
            message_at=datetime.now(timezone.utc),
        )

        # Auto-reopen on inbound messages
        if direction == MessageDirection.inbound:
            from app.services.conversation_state_engine import reopen_on_new_message
            await reopen_on_new_message(db, conversation)

    # Update unread counts
    await _increment_unread_counts(db, conversation_id, workspace_id, sender_id)

    await db.commit()
    await db.refresh(message)
    return message


async def create_inbound_message(
    db: AsyncSession,
    workspace_id: int,
    contact_id: int,
    content: str,
    content_type: MessageContentType = MessageContentType.text,
    provider_message_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> tuple[ConversationMessage, Conversation]:
    """
    Process an inbound message from a contact.

    1. Get or create conversation
    2. Create message
    3. Return both for downstream processing
    """
    from app.models.conversation import ConversationChannel
    conversation, created = await conversation_service.get_or_create_conversation(
        db, workspace_id, contact_id, ConversationChannel.whatsapp
    )

    message = await create_message(
        db=db,
        conversation_id=conversation.id,
        workspace_id=workspace_id,
        direction=MessageDirection.inbound,
        sender_type=MessageSenderType.contact,
        sender_id=contact_id,
        content=content,
        content_type=content_type,
        provider_message_id=provider_message_id,
        metadata_json=metadata_json,
    )

    return message, conversation


async def create_outbound_message(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    agent_user_id: int,
    content: str,
    content_type: MessageContentType = MessageContentType.text,
    provider_message_id: str | None = None,
    metadata_json: dict[str, Any] | None = None,
) -> ConversationMessage:
    """Create an outbound message sent by an agent."""
    return await create_message(
        db=db,
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        direction=MessageDirection.outbound,
        sender_type=MessageSenderType.agent,
        sender_id=agent_user_id,
        content=content,
        content_type=content_type,
        provider_message_id=provider_message_id,
        metadata_json=metadata_json,
    )


async def list_messages(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    limit: int = 50,
    before_id: int | None = None,
    after_id: int | None = None,
) -> list[ConversationMessage]:
    """
    List messages in a conversation with cursor-based pagination.
    """
    query = select(ConversationMessage).where(
        and_(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.workspace_id == workspace_id,
        )
    )

    if before_id:
        query = query.where(ConversationMessage.id < before_id)
    if after_id:
        query = query.where(ConversationMessage.id > after_id)

    # Most recent messages first (for before_id), oldest first (for after_id)
    if after_id:
        query = query.order_by(ConversationMessage.created_at.asc())
    else:
        query = query.order_by(ConversationMessage.created_at.desc())

    query = query.limit(limit)
    result = await db.execute(query)
    messages = list(result.scalars().all())

    # Reverse for consistent chronological order when paginating backwards
    if not after_id:
        messages.reverse()

    return messages


async def get_message_count(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
) -> int:
    stmt = select(func.count()).where(
        and_(
            ConversationMessage.conversation_id == conversation_id,
            ConversationMessage.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar() or 0


async def find_message_by_provider_id(
    db: AsyncSession,
    provider_message_id: str,
) -> ConversationMessage | None:
    """Find a conversation message by its provider (Meta) message ID."""
    stmt = select(ConversationMessage).where(
        ConversationMessage.provider_message_id == provider_message_id
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def _increment_unread_counts(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    sender_id: int | None,
) -> None:
    """Increment unread count for all agents tracking this conversation (except sender)."""
    stmt = select(ConversationUnreadState).where(
        and_(
            ConversationUnreadState.conversation_id == conversation_id,
            ConversationUnreadState.workspace_id == workspace_id,
        )
    )

    if sender_id:
        stmt = stmt.where(ConversationUnreadState.user_id != sender_id)

    result = await db.execute(stmt)
    unread_states = list(result.scalars().all())

    for state in unread_states:
        state.unread_count += 1
        state.updated_at = datetime.now(timezone.utc)
