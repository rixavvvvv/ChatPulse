"""
Conversation Note Service

Internal notes on conversations — visible only to agents.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import ConversationInternalNote

logger = logging.getLogger(__name__)


async def create_note(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    author_user_id: int,
    body: str,
) -> ConversationInternalNote:
    note = ConversationInternalNote(
        conversation_id=conversation_id,
        workspace_id=workspace_id,
        author_user_id=author_user_id,
        body=body,
    )
    db.add(note)
    await db.commit()
    await db.refresh(note)
    return note


async def list_notes(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
    include_deleted: bool = False,
) -> list[ConversationInternalNote]:
    query = select(ConversationInternalNote).where(
        and_(
            ConversationInternalNote.conversation_id == conversation_id,
            ConversationInternalNote.workspace_id == workspace_id,
        )
    )
    if not include_deleted:
        query = query.where(ConversationInternalNote.deleted_at.is_(None))

    query = query.order_by(ConversationInternalNote.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def delete_note(
    db: AsyncSession,
    note_id: int,
    conversation_id: int,
    workspace_id: int,
) -> ConversationInternalNote | None:
    """Soft delete a note."""
    stmt = select(ConversationInternalNote).where(
        and_(
            ConversationInternalNote.id == note_id,
            ConversationInternalNote.conversation_id == conversation_id,
            ConversationInternalNote.workspace_id == workspace_id,
            ConversationInternalNote.deleted_at.is_(None),
        )
    )
    result = await db.execute(stmt)
    note = result.scalar_one_or_none()

    if note:
        note.deleted_at = datetime.now(timezone.utc)
        await db.commit()
        await db.refresh(note)

    return note
