from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.webhook_ingestion import (
    WebhookIngestion,
    WebhookIngestionStatus,
    WebhookSource,
)
from app.services.webhook_verification import payload_sha256, webhook_dedupe_key

settings = get_settings()


async def find_recent_duplicate_ingestion(
    session: AsyncSession,
    *,
    source: str,
    dedupe_key: str,
) -> WebhookIngestion | None:
    """Short-window dedupe for provider retries (same body)."""
    since = datetime.now(tz=UTC) - timedelta(seconds=settings.webhook_dedupe_ttl_seconds)
    stmt = (
        select(WebhookIngestion)
        .where(
            WebhookIngestion.source == source,
            WebhookIngestion.dedupe_key == dedupe_key,
            WebhookIngestion.received_at >= since,
            WebhookIngestion.processing_status.in_(
                (
                    WebhookIngestionStatus.queued.value,
                    WebhookIngestionStatus.processing.value,
                    WebhookIngestionStatus.completed.value,
                )
            ),
        )
        .order_by(WebhookIngestion.id.desc())
        .limit(1)
    )
    return (await session.execute(stmt)).scalar_one_or_none()


async def create_webhook_ingestion(
    session: AsyncSession,
    *,
    source: str,
    raw_body: bytes,
    payload_json: dict[str, Any] | list[Any],
    store_identifier: str | None,
    verification_passed: bool,
    verification_error: str | None,
    headers_meta: dict[str, Any] | None,
    workspace_id: int | None = None,
    persist_raw_body: bool = False,
    provider_signature: str | None = None,
    provider_event_id: str | None = None,
) -> WebhookIngestion:
    dedupe = webhook_dedupe_key(
        source=source,
        raw_body=raw_body,
        store_fragment=store_identifier,
    )
    row = WebhookIngestion(
        source=source,
        provider_event_id=provider_event_id or dedupe,
        dedupe_key=dedupe,
        store_identifier=store_identifier,
        payload_sha256=payload_sha256(raw_body),
        payload_json=payload_json,
        raw_body=raw_body if persist_raw_body else None,
        provider_signature=provider_signature,
        headers_meta=headers_meta,
        verification_passed=verification_passed,
        verification_error=verification_error,
        processing_status=(
            WebhookIngestionStatus.verified.value
            if verification_passed
            else WebhookIngestionStatus.received.value
        ),
        workspace_id=workspace_id,
    )
    session.add(row)
    await session.flush()
    return row


def enqueue_webhook_dispatch_task(ingestion_id: int) -> str:
    """Schedule async dispatch; returns Celery task id."""
    from app.queue.webhook_tasks import process_webhook_ingestion

    async_result = process_webhook_ingestion.delay(ingestion_id)
    return async_result.id


async def mark_ingestion_queued(
    session: AsyncSession,
    row: WebhookIngestion,
    *,
    celery_task_id: str | None,
) -> None:
    row.processing_status = WebhookIngestionStatus.queued.value
    row.celery_task_id = celery_task_id
    row.updated_at = datetime.now(tz=UTC)


async def mark_ingestion_processing(session: AsyncSession, row: WebhookIngestion) -> None:
    row.processing_status = WebhookIngestionStatus.processing.value
    row.updated_at = datetime.now(tz=UTC)


async def mark_ingestion_completed(
    session: AsyncSession,
    row: WebhookIngestion,
    *,
    dispatch_result: dict[str, Any] | None,
) -> None:
    row.processing_status = WebhookIngestionStatus.completed.value
    row.dispatch_result = dispatch_result
    row.completed_at = datetime.now(tz=UTC)
    row.error_message = None
    row.updated_at = datetime.now(tz=UTC)


async def mark_ingestion_failed(
    session: AsyncSession,
    row: WebhookIngestion,
    *,
    message: str,
    dead: bool = False,
) -> None:
    row.processing_status = (
        WebhookIngestionStatus.dead.value if dead else WebhookIngestionStatus.failed.value
    )
    row.error_message = message[:8192]
    row.completed_at = datetime.now(tz=UTC)
    row.updated_at = datetime.now(tz=UTC)


async def get_ingestion_by_id(
    session: AsyncSession,
    ingestion_id: int,
) -> WebhookIngestion | None:
    return await session.get(WebhookIngestion, ingestion_id)


async def replay_webhook_ingestions(
    session: AsyncSession,
    *,
    ingestion_ids: list[int],
) -> list[dict[str, Any]]:
    """Reset failed ingestions to queued and enqueue a new dispatch task.

    REPLAY-SAFE: Each replay increments replay_count and sets last_replay_at.
    Provider-level idempotency prevents duplicate processing of replayed webhooks.
    """
    from app.services.webhook_idempotency_service import get_idempotency_service

    results: list[dict[str, Any]] = []
    terminal = (
        WebhookIngestionStatus.failed.value,
        WebhookIngestionStatus.dead.value,
    )
    service = get_idempotency_service()

    for ingestion_id in ingestion_ids:
        row = await get_ingestion_by_id(session, ingestion_id)
        if not row:
            results.append({"ingestion_id": ingestion_id, "error": "not_found"})
            continue
        if row.processing_status not in terminal:
            results.append(
                {
                    "ingestion_id": ingestion_id,
                    "error": "replay_only_failed_or_dead",
                    "processing_status": row.processing_status,
                }
            )
            continue

        # REPLAY-SAFE: Release Redis lock before replay
        # This allows the replayed webhook to be processed again
        if row.provider_event_id:
            try:
                await service.release_lock(
                    source=row.source,
                    provider_event_id=row.provider_event_id,
                )
            except Exception:
                pass

        row.processing_status = WebhookIngestionStatus.queued.value
        row.replay_count = int(row.replay_count or 0) + 1
        row.last_replay_at = datetime.now(tz=UTC)
        row.error_message = None
        row.completed_at = None
        row.dispatch_result = None
        task_id = enqueue_webhook_dispatch_task(row.id)
        row.celery_task_id = task_id
        await session.commit()
        results.append(
            {
                "ingestion_id": ingestion_id,
                "status": "requeued",
                "celery_task_id": task_id,
                "replay_count": row.replay_count,
            }
        )
    return results
