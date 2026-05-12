from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_intelligence import ContactNote


async def add_contact_note(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    author_user_id: int | None,
    body: str,
) -> ContactNote:
    text = body.strip()
    if not text:
        raise ValueError("Note body is required")
    row = ContactNote(
        workspace_id=workspace_id,
        contact_id=contact_id,
        author_user_id=author_user_id,
        body=text,
    )
    session.add(row)
    await session.commit()
    await session.refresh(row)
    return row


async def list_contact_notes(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    include_deleted: bool = False,
) -> list[ContactNote]:
    stmt = select(ContactNote).where(
        ContactNote.workspace_id == workspace_id,
        ContactNote.contact_id == contact_id,
    )
    if not include_deleted:
        stmt = stmt.where(ContactNote.deleted_at.is_(None))
    stmt = stmt.order_by(ContactNote.created_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def soft_delete_contact_note(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    note_id: int,
) -> bool:
    stmt = select(ContactNote).where(
        ContactNote.id == note_id,
        ContactNote.workspace_id == workspace_id,
        ContactNote.contact_id == contact_id,
        ContactNote.deleted_at.is_(None),
    )
    row = (await session.execute(stmt)).scalar_one_or_none()
    if not row:
        return False
    row.deleted_at = datetime.now(tz=UTC)
    await session.commit()
    return True

