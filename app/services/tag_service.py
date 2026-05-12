from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_intelligence import ContactTag, Tag


async def create_tag(
    session: AsyncSession,
    *,
    workspace_id: int,
    name: str,
    color: str | None,
) -> Tag:
    normalized = name.strip()
    if not normalized:
        raise ValueError("Tag name is required")
    tag = Tag(workspace_id=workspace_id, name=normalized, color=(color or None))
    session.add(tag)
    try:
        await session.commit()
        await session.refresh(tag)
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Tag name already exists") from exc
    return tag


async def list_tags(session: AsyncSession, *, workspace_id: int) -> list[Tag]:
    stmt = select(Tag).where(Tag.workspace_id == workspace_id).order_by(Tag.name.asc())
    return list((await session.execute(stmt)).scalars().all())


async def get_tag_by_name(
    session: AsyncSession,
    *,
    workspace_id: int,
    name: str,
) -> Tag | None:
    stmt = select(Tag).where(Tag.workspace_id == workspace_id, Tag.name == name.strip())
    return (await session.execute(stmt)).scalar_one_or_none()


async def ensure_tag(
    session: AsyncSession,
    *,
    workspace_id: int,
    name: str,
) -> Tag:
    existing = await get_tag_by_name(session, workspace_id=workspace_id, name=name)
    if existing:
        return existing
    return await create_tag(session, workspace_id=workspace_id, name=name, color=None)


async def set_contact_tags(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    tag_names: list[str],
) -> list[Tag]:
    cleaned = []
    seen = set()
    for raw in tag_names:
        name = (raw or "").strip()
        if not name or name in seen:
            continue
        seen.add(name)
        cleaned.append(name)

    # fetch existing links
    existing_stmt = select(ContactTag).where(
        ContactTag.workspace_id == workspace_id,
        ContactTag.contact_id == contact_id,
    )
    existing = list((await session.execute(existing_stmt)).scalars().all())
    existing_by_tag: dict[int, ContactTag] = {row.tag_id: row for row in existing}

    tags: list[Tag] = []
    keep_tag_ids: set[int] = set()
    for name in cleaned:
        tag = await ensure_tag(session, workspace_id=workspace_id, name=name)
        tags.append(tag)
        keep_tag_ids.add(tag.id)
        if tag.id not in existing_by_tag:
            session.add(
                ContactTag(
                    workspace_id=workspace_id,
                    contact_id=contact_id,
                    tag_id=tag.id,
                )
            )

    # remove links not in keep list
    for row in existing:
        if row.tag_id not in keep_tag_ids:
            await session.delete(row)

    await session.commit()
    return tags

