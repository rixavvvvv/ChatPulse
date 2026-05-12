from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact_intelligence import (
    AttributeDefinition,
    ContactAttributeType,
    ContactAttributeValue,
)


def _parse_iso_datetime(value: str | None) -> datetime | None:
    if value is None:
        return None
    cleaned = value.strip()
    if not cleaned:
        return None
    try:
        # Accept both date and datetime ISO strings.
        return datetime.fromisoformat(cleaned.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("value_date_iso must be an ISO date/datetime") from exc


async def create_attribute_definition(
    session: AsyncSession,
    *,
    workspace_id: int,
    key: str,
    label: str,
    type: str,
    is_indexed: bool,
) -> AttributeDefinition:
    normalized_key = key.strip()
    if not normalized_key:
        raise ValueError("Attribute key is required")
    normalized_label = label.strip()
    if not normalized_label:
        raise ValueError("Attribute label is required")
    normalized_type = type.strip().lower()
    if normalized_type not in {t.value for t in ContactAttributeType}:
        raise ValueError("Invalid attribute type")

    row = AttributeDefinition(
        workspace_id=workspace_id,
        key=normalized_key,
        label=normalized_label,
        type=normalized_type,
        is_indexed=bool(is_indexed),
    )
    session.add(row)
    try:
        await session.commit()
        await session.refresh(row)
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Attribute key already exists") from exc
    return row


async def list_attribute_definitions(
    session: AsyncSession,
    *,
    workspace_id: int,
) -> list[AttributeDefinition]:
    stmt = (
        select(AttributeDefinition)
        .where(AttributeDefinition.workspace_id == workspace_id)
        .order_by(AttributeDefinition.key.asc())
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_attribute_definition_by_key(
    session: AsyncSession,
    *,
    workspace_id: int,
    key: str,
) -> AttributeDefinition | None:
    stmt = select(AttributeDefinition).where(
        AttributeDefinition.workspace_id == workspace_id,
        AttributeDefinition.key == key.strip(),
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def upsert_contact_attribute(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
    definition: AttributeDefinition,
    value_text: str | None,
    value_number: float | None,
    value_bool: bool | None,
    value_date_iso: str | None,
) -> ContactAttributeValue:
    dt = _parse_iso_datetime(value_date_iso)

    stmt = select(ContactAttributeValue).where(
        ContactAttributeValue.workspace_id == workspace_id,
        ContactAttributeValue.contact_id == contact_id,
        ContactAttributeValue.attribute_definition_id == definition.id,
    )
    existing = (await session.execute(stmt)).scalar_one_or_none()
    if existing is None:
        existing = ContactAttributeValue(
            workspace_id=workspace_id,
            contact_id=contact_id,
            attribute_definition_id=definition.id,
        )
        session.add(existing)

    # Reset all value columns then set one (based on definition.type).
    existing.value_text = None
    existing.value_number = None
    existing.value_bool = None
    existing.value_date = None

    if definition.type == ContactAttributeType.text.value:
        existing.value_text = (value_text or "").strip() or None
    elif definition.type == ContactAttributeType.number.value:
        existing.value_number = value_number
    elif definition.type == ContactAttributeType.boolean.value:
        existing.value_bool = value_bool
    elif definition.type == ContactAttributeType.date.value:
        existing.value_date = dt

    await session.commit()
    await session.refresh(existing)
    return existing


async def list_contact_attributes(
    session: AsyncSession,
    *,
    workspace_id: int,
    contact_id: int,
) -> list[tuple[AttributeDefinition, ContactAttributeValue]]:
    defs_stmt = select(AttributeDefinition).where(
        AttributeDefinition.workspace_id == workspace_id
    )
    definitions = list((await session.execute(defs_stmt)).scalars().all())
    if not definitions:
        return []

    values_stmt = select(ContactAttributeValue).where(
        ContactAttributeValue.workspace_id == workspace_id,
        ContactAttributeValue.contact_id == contact_id,
    )
    values = list((await session.execute(values_stmt)).scalars().all())
    by_def_id = {v.attribute_definition_id: v for v in values}

    out: list[tuple[AttributeDefinition, ContactAttributeValue]] = []
    for d in definitions:
        v = by_def_id.get(d.id)
        if v:
            out.append((d, v))
    return out

