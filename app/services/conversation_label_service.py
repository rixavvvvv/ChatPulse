"""
Conversation Label Service

Label CRUD and assignment to conversations.
"""

import logging
from datetime import datetime, timezone

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import (
    ConversationLabel,
    ConversationLabelAssignment,
)

logger = logging.getLogger(__name__)


async def create_label(
    db: AsyncSession,
    workspace_id: int,
    name: str,
    color: str = "#6B7280",
    description: str | None = None,
) -> ConversationLabel:
    label = ConversationLabel(
        workspace_id=workspace_id,
        name=name,
        color=color,
        description=description,
    )
    db.add(label)
    await db.commit()
    await db.refresh(label)
    return label


async def list_labels(
    db: AsyncSession,
    workspace_id: int,
) -> list[ConversationLabel]:
    stmt = (
        select(ConversationLabel)
        .where(ConversationLabel.workspace_id == workspace_id)
        .order_by(ConversationLabel.name)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_label_by_id(
    db: AsyncSession,
    label_id: int,
    workspace_id: int,
) -> ConversationLabel | None:
    stmt = select(ConversationLabel).where(
        and_(
            ConversationLabel.id == label_id,
            ConversationLabel.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def delete_label(
    db: AsyncSession,
    label_id: int,
    workspace_id: int,
) -> bool:
    label = await get_label_by_id(db, label_id, workspace_id)
    if label:
        await db.delete(label)
        await db.commit()
        return True
    return False


async def assign_label(
    db: AsyncSession,
    conversation_id: int,
    label_id: int,
    workspace_id: int,
) -> ConversationLabelAssignment:
    # Check if already assigned
    existing = await db.execute(
        select(ConversationLabelAssignment).where(
            and_(
                ConversationLabelAssignment.conversation_id == conversation_id,
                ConversationLabelAssignment.label_id == label_id,
            )
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Label already assigned to this conversation")

    assignment = ConversationLabelAssignment(
        conversation_id=conversation_id,
        label_id=label_id,
        workspace_id=workspace_id,
    )
    db.add(assignment)
    await db.commit()
    await db.refresh(assignment)
    return assignment


async def unassign_label(
    db: AsyncSession,
    conversation_id: int,
    label_id: int,
) -> bool:
    stmt = select(ConversationLabelAssignment).where(
        and_(
            ConversationLabelAssignment.conversation_id == conversation_id,
            ConversationLabelAssignment.label_id == label_id,
        )
    )
    result = await db.execute(stmt)
    assignment = result.scalar_one_or_none()

    if assignment:
        await db.delete(assignment)
        await db.commit()
        return True
    return False


async def get_conversation_labels(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
) -> list[ConversationLabel]:
    stmt = (
        select(ConversationLabel)
        .join(
            ConversationLabelAssignment,
            ConversationLabelAssignment.label_id == ConversationLabel.id,
        )
        .where(
            ConversationLabelAssignment.conversation_id == conversation_id,
        )
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())
