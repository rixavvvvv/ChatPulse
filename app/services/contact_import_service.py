from __future__ import annotations

import csv
import io
import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.contact_intelligence import ContactImportJob, ContactImportRow, ContactImportStatus
from app.services.contact_activity_service import record_contact_activity
from app.services.contact_service import normalize_phone
from app.services.tag_service import set_contact_tags

logger = logging.getLogger(__name__)


def _get_column_name(fieldnames: list[str] | None, target: str) -> str | None:
    if not fieldnames:
        return None
    for column in fieldnames:
        if column and column.strip().lower() == target:
            return column
    return None


async def create_contact_import_job_from_csv(
    session: AsyncSession,
    *,
    workspace_id: int,
    created_by_user_id: int | None,
    original_filename: str | None,
    file_bytes: bytes,
) -> ContactImportJob:
    try:
        decoded = file_bytes.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("CSV must be UTF-8 encoded") from exc

    reader = csv.DictReader(io.StringIO(decoded))
    name_column = _get_column_name(reader.fieldnames, "name")
    phone_column = _get_column_name(reader.fieldnames, "phone")
    tags_column = _get_column_name(reader.fieldnames, "tags")

    if not name_column or not phone_column:
        raise ValueError("CSV must contain name and phone columns")

    job = ContactImportJob(
        workspace_id=workspace_id,
        created_by_user_id=created_by_user_id,
        original_filename=(original_filename or None),
        status=ContactImportStatus.queued.value,
        total_rows=0,
        processed_rows=0,
        inserted_rows=0,
        skipped_rows=0,
        failed_rows=0,
    )
    session.add(job)
    await session.flush()

    rows: list[ContactImportRow] = []
    row_number = 0
    for raw in reader:
        row_number += 1
        name = (raw.get(name_column) or "").strip()
        phone_raw = (raw.get(phone_column) or "").strip()
        tags_raw = (raw.get(tags_column) or "").strip() if tags_column else ""
        rows.append(
            ContactImportRow(
                job_id=job.id,
                row_number=row_number,
                raw={
                    "name": name,
                    "phone": phone_raw,
                    "tags": tags_raw,
                },
                status="queued",
                error=None,
            )
        )

    job.total_rows = len(rows)
    session.add_all(rows)
    await session.commit()
    await session.refresh(job)
    return job


async def list_contact_import_jobs(
    session: AsyncSession,
    *,
    workspace_id: int,
    limit: int = 20,
) -> list[ContactImportJob]:
    cap = max(1, min(limit, 100))
    stmt = (
        select(ContactImportJob)
        .where(ContactImportJob.workspace_id == workspace_id)
        .order_by(ContactImportJob.id.desc())
        .limit(cap)
    )
    return list((await session.execute(stmt)).scalars().all())


async def get_contact_import_job(
    session: AsyncSession,
    *,
    workspace_id: int,
    job_id: int,
) -> ContactImportJob | None:
    stmt = select(ContactImportJob).where(
        ContactImportJob.workspace_id == workspace_id,
        ContactImportJob.id == job_id,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def list_contact_import_row_errors(
    session: AsyncSession,
    *,
    job_id: int,
    limit: int = 200,
) -> list[ContactImportRow]:
    cap = max(1, min(limit, 500))
    stmt = (
        select(ContactImportRow)
        .where(ContactImportRow.job_id == job_id, ContactImportRow.error.is_not(None))
        .order_by(ContactImportRow.row_number.asc())
        .limit(cap)
    )
    return list((await session.execute(stmt)).scalars().all())


async def run_contact_import_job(
    session: AsyncSession,
    *,
    workspace_id: int,
    job_id: int,
) -> dict:
    job = await get_contact_import_job(session, workspace_id=workspace_id, job_id=job_id)
    if not job:
        return {"error": "job_not_found"}

    if job.status in {ContactImportStatus.completed.value, ContactImportStatus.failed.value}:
        return {"status": job.status}

    job.status = ContactImportStatus.processing.value
    await session.commit()

    rows_stmt = select(ContactImportRow).where(ContactImportRow.job_id == job_id).order_by(
        ContactImportRow.row_number.asc()
    )
    rows = list((await session.execute(rows_stmt)).scalars().all())

    inserted = 0
    skipped = 0
    failed = 0
    processed = 0

    for r in rows:
        processed += 1
        raw = r.raw or {}
        name = str(raw.get("name") or "").strip()
        phone_raw = str(raw.get("phone") or "").strip()
        tags_raw = str(raw.get("tags") or "").strip()

        normalized_phone = normalize_phone(phone_raw)
        if not name or not normalized_phone:
            r.status = "skipped"
            r.error = "Missing name or invalid phone"
            skipped += 1
        else:
            existing_stmt = select(Contact).where(
                Contact.workspace_id == workspace_id,
                Contact.phone == normalized_phone,
            )
            existing = (await session.execute(existing_stmt)).scalar_one_or_none()
            if existing:
                r.status = "skipped"
                r.error = "Contact already exists"
                skipped += 1
            else:
                try:
                    contact = Contact(
                        workspace_id=workspace_id,
                        name=name,
                        phone=normalized_phone,
                        tags=[],
                    )
                    session.add(contact)
                    await session.flush()

                    tag_names = [t.strip() for t in tags_raw.split(",") if t.strip()]
                    if tag_names:
                        await set_contact_tags(
                            session,
                            workspace_id=workspace_id,
                            contact_id=contact.id,
                            tag_names=tag_names,
                        )
                        # Keep legacy array in sync for existing UI payloads.
                        contact.tags = tag_names
                    await record_contact_activity(
                        session,
                        workspace_id=workspace_id,
                        contact_id=contact.id,
                        actor_user_id=job.created_by_user_id,
                        type="created",
                        payload={"source": "csv_import", "job_id": job_id},
                    )
                    r.status = "inserted"
                    r.error = None
                    inserted += 1
                except Exception as exc:  # pragma: no cover
                    await session.rollback()
                    r.status = "failed"
                    r.error = str(exc)
                    failed += 1

        job.processed_rows = processed
        job.inserted_rows = inserted
        job.skipped_rows = skipped
        job.failed_rows = failed
        await session.commit()

    job.status = ContactImportStatus.completed.value if failed == 0 else ContactImportStatus.failed.value
    job.completed_at = datetime.now(tz=UTC)
    await session.commit()
    return {
        "status": job.status,
        "processed_rows": job.processed_rows,
        "inserted_rows": job.inserted_rows,
        "skipped_rows": job.skipped_rows,
        "failed_rows": job.failed_rows,
    }

