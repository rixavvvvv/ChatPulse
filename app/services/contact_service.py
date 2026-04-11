import csv
import io
import re

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.schemas.contact import ContactUploadResponse

PHONE_PATTERN = re.compile(r"^\+?[1-9]\d{7,14}$")


def normalize_phone(phone: str) -> str | None:
    raw = phone.strip()
    if not raw:
        return None

    if raw.startswith("+"):
        normalized = "+" + "".join(ch for ch in raw[1:] if ch.isdigit())
    else:
        normalized = "".join(ch for ch in raw if ch.isdigit())

    if not PHONE_PATTERN.match(normalized):
        return None

    return normalized


def _get_column_name(fieldnames: list[str] | None, target: str) -> str | None:
    if not fieldnames:
        return None

    for column in fieldnames:
        if column and column.strip().lower() == target:
            return column

    return None


async def import_contacts_from_csv(
    session: AsyncSession,
    file_bytes: bytes,
    workspace_id: int,
) -> ContactUploadResponse:
    try:
        decoded = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    name_column = _get_column_name(reader.fieldnames, "name")
    phone_column = _get_column_name(reader.fieldnames, "phone")

    if not name_column or not phone_column:
        raise ValueError("CSV must contain name and phone columns")

    parsed_contacts: list[tuple[str, str]] = []
    seen_phones: set[str] = set()
    skipped = 0

    for row in reader:
        name = (row.get(name_column) or "").strip()
        phone_raw = (row.get(phone_column) or "").strip()
        normalized_phone = normalize_phone(phone_raw)

        if not name or not normalized_phone:
            skipped += 1
            continue

        if normalized_phone in seen_phones:
            skipped += 1
            continue

        seen_phones.add(normalized_phone)
        parsed_contacts.append((name, normalized_phone))

    if not parsed_contacts:
        return ContactUploadResponse(contacts_added=0, contacts_skipped=skipped)

    candidate_phones = [phone for _, phone in parsed_contacts]
    existing_stmt = select(Contact.phone).where(
        Contact.workspace_id == workspace_id,
        Contact.phone.in_(candidate_phones),
    )
    existing_phones = set((await session.execute(existing_stmt)).scalars().all())

    contacts_to_insert = [
        Contact(workspace_id=workspace_id, name=name, phone=phone, tags=[])
        for name, phone in parsed_contacts
        if phone not in existing_phones
    ]
    skipped += len(parsed_contacts) - len(contacts_to_insert)

    if not contacts_to_insert:
        return ContactUploadResponse(contacts_added=0, contacts_skipped=skipped)

    session.add_all(contacts_to_insert)

    try:
        await session.commit()
        return ContactUploadResponse(
            contacts_added=len(contacts_to_insert),
            contacts_skipped=skipped,
        )
    except IntegrityError:
        await session.rollback()

    added = 0
    for contact in contacts_to_insert:
        session.add(contact)
        try:
            await session.commit()
            added += 1
        except IntegrityError:
            await session.rollback()
            skipped += 1

    return ContactUploadResponse(contacts_added=added, contacts_skipped=skipped)


async def create_contact(
    session: AsyncSession,
    workspace_id: int,
    name: str,
    phone: str,
    tags: list[str] | None = None,
) -> Contact:
    normalized_phone = normalize_phone(phone)
    if not normalized_phone:
        raise ValueError("Invalid phone number format. Use E.164 style like +14155550101")

    normalized_name = name.strip()
    if not normalized_name:
        raise ValueError("Contact name is required")

    normalized_tags = [tag.strip() for tag in (tags or []) if tag.strip()]

    contact = Contact(
        workspace_id=workspace_id,
        name=normalized_name,
        phone=normalized_phone,
        tags=normalized_tags,
    )
    session.add(contact)

    try:
        await session.commit()
        await session.refresh(contact)
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("Contact with this phone already exists in the workspace") from exc

    return contact


async def list_contacts(
    session: AsyncSession,
    workspace_id: int,
) -> list[Contact]:
    stmt = (
        select(Contact)
        .where(Contact.workspace_id == workspace_id)
        .order_by(Contact.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
