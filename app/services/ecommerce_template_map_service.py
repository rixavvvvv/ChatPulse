from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.ecommerce import EcommerceEventTemplateMap
from app.models.template import Template


async def upsert_event_template_map(
    session: AsyncSession,
    *,
    workspace_id: int,
    event_type: str,
    template_id: int,
) -> EcommerceEventTemplateMap:
    event = event_type.strip().lower()
    if not event:
        raise ValueError("event_type is required")

    template = await session.get(Template, template_id)
    if not template or template.workspace_id != workspace_id:
        raise ValueError("Template not found in workspace")

    stmt = select(EcommerceEventTemplateMap).where(
        EcommerceEventTemplateMap.workspace_id == workspace_id,
        EcommerceEventTemplateMap.event_type == event,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()

    if existing:
        existing.template_id = template_id
        await session.commit()
        await session.refresh(existing)
        return existing

    row = EcommerceEventTemplateMap(
        workspace_id=workspace_id,
        event_type=event,
        template_id=template_id,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Failed to save event template mapping") from exc
    await session.refresh(row)
    return row


async def get_template_for_event(
    session: AsyncSession,
    *,
    workspace_id: int,
    event_type: str,
) -> Template | None:
    event = event_type.strip().lower()
    stmt = (
        select(Template)
        .join(
            EcommerceEventTemplateMap,
            EcommerceEventTemplateMap.template_id == Template.id,
        )
        .where(
            EcommerceEventTemplateMap.workspace_id == workspace_id,
            EcommerceEventTemplateMap.event_type == event,
        )
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_event_maps(
    session: AsyncSession,
    *,
    workspace_id: int,
) -> list[EcommerceEventTemplateMap]:
    stmt = select(EcommerceEventTemplateMap).where(
        EcommerceEventTemplateMap.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
