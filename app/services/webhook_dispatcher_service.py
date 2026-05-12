from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_ingestion import WebhookIngestion, WebhookIngestionStatus, WebhookSource
from app.services.domain_event_service import insert_domain_events_for_ingestion
from app.services.order_webhook_service import process_order_created_webhook
from app.services.webhook_idempotency_service import get_idempotency_service
from app.services.webhook_ingestion_service import (
    mark_ingestion_completed,
    mark_ingestion_failed,
    mark_ingestion_processing,
)
from app.services.webhook_service import process_meta_webhook_payload

logger = logging.getLogger(__name__)


class _SignatureHeadersProxy:
    """Minimal header mapping for Shopify HMAC verification in the worker."""

    __slots__ = ("_sig",)

    def __init__(self, signature: str) -> None:
        self._sig = signature

    def get(self, key: str, default: str | None = None) -> str | None:
        kl = str(key).lower()
        if kl in (
            "x-shopify-hmac-sha256",
            "x-webhook-signature",
            "x-signature",
        ):
            return self._sig
        return default


async def dispatch_webhook_ingestion(
    session: AsyncSession,
    row: WebhookIngestion,
) -> dict[str, Any]:
    """Run provider-specific side effects and attach normalized domain events.

    REPLAY-SAFE: Uses provider-level idempotency to prevent duplicate processing
    even when webhooks are replayed after failure.
    """
    # REPLAY-SAFE: Skip if already completed (authoritative check)
    if row.processing_status == WebhookIngestionStatus.completed.value:
        return dict(row.dispatch_result or {"status": "already_completed"})

    await mark_ingestion_processing(session, row)

    # REPLAY-SAFE: Mark in Redis as processing to prevent duplicate execution
    # if another worker picks up this task during visibility timeout
    if row.provider_event_id:
        service = get_idempotency_service()
        await service.mark_processing(
            source=row.source,
            provider_event_id=row.provider_event_id,
            ingestion_id=row.id,
        )

    await session.commit()

    source = row.source
    summary: dict[str, Any] = {"source": source, "ingestion_id": row.id}

    try:
        if source == WebhookSource.meta_whatsapp.value:
            summary.update(await _dispatch_meta(session, row))
        elif source == WebhookSource.shopify_orders.value:
            summary.update(await _dispatch_shopify(session, row))
        else:
            raise RuntimeError(f"Unknown webhook source: {source}")

        st = summary.get("status")
        reason = summary.get("reason")
        if st == "unauthorized" or (
            st == "failed" and reason == "missing_provider_signature"
        ):
            await mark_ingestion_failed(
                session,
                row,
                message=str(reason or st or "dispatch_failed"),
                dead=False,
            )
        else:
            await mark_ingestion_completed(session, row, dispatch_result=summary)

            # REPLAY-SAFE: Mark as completed in Redis for fast future checks
            if row.provider_event_id:
                await service.mark_completed(
                    source=row.source,
                    provider_event_id=row.provider_event_id,
                    ingestion_id=row.id,
                )

        await session.commit()
        return summary
    except OperationalError:
        await session.rollback()
        raise
    except Exception as exc:
        logger.exception("Webhook dispatch failed ingestion_id=%s", row.id)
        await mark_ingestion_failed(session, row, message=str(exc), dead=False)

        # REPLAY-SAFE: Release lock to allow retry
        if row.provider_event_id:
            try:
                await service.release_lock(
                    source=row.source,
                    provider_event_id=row.provider_event_id,
                )
            except Exception:
                pass

        await session.commit()
        summary["error"] = str(exc)
        return summary


async def _dispatch_meta(session: AsyncSession, row: WebhookIngestion) -> dict[str, Any]:
    payload = row.payload_json
    if not isinstance(payload, dict):
        return {"status": "ignored", "reason": "non_object_payload"}

    object_type = payload.get("object")
    if object_type is not None and object_type != "whatsapp_business_account":
        await insert_domain_events_for_ingestion(
            session,
            webhook_ingestion_id=row.id,
            events=[
                (
                    "meta.webhook.ignored_object",
                    None,
                    {"object": object_type},
                    f"ignored:{row.id}:{object_type}",
                )
            ],
        )
        await session.commit()
        return {
            "status": "ignored",
            "object": object_type,
            "processed": 0,
            "ignored": 0,
            "unknown_message": 0,
        }

    result = await process_meta_webhook_payload(session=session, payload=payload)
    domain_events: list[tuple[str, int | None, dict[str, Any], str | None]] = [
        (
            "meta.webhook.batch",
            None,
            {
                "processed": result.processed,
                "ignored": result.ignored,
                "unknown_message": result.unknown_message,
            },
            f"batch:{row.id}",
        )
    ]
    domain_events.extend(result.domain_events)
    await insert_domain_events_for_ingestion(
        session, webhook_ingestion_id=row.id, events=domain_events
    )
    await session.commit()
    return {
        "status": "ok",
        "processed": result.processed,
        "ignored": result.ignored,
        "unknown_message": result.unknown_message,
    }


async def _dispatch_shopify(session: AsyncSession, row: WebhookIngestion) -> dict[str, Any]:
    store = (row.store_identifier or "").strip()
    if not store:
        await insert_domain_events_for_ingestion(
            session,
            webhook_ingestion_id=row.id,
            events=[
                (
                    "shopify.order_webhook.skipped",
                    row.workspace_id,
                    {"reason": "missing_store_identifier"},
                    f"skip:{row.id}:store",
                )
            ],
        )
        await session.commit()
        return {"status": "skipped", "reason": "missing_store_identifier"}

    raw_body = row.raw_body
    if not raw_body:
        await insert_domain_events_for_ingestion(
            session,
            webhook_ingestion_id=row.id,
            events=[
                (
                    "shopify.order_webhook.skipped",
                    row.workspace_id,
                    {"reason": "missing_raw_body"},
                    f"skip:{row.id}:raw",
                )
            ],
        )
        await session.commit()
        return {"status": "skipped", "reason": "missing_raw_body"}

    sig = (row.provider_signature or "").strip()
    if not sig:
        return {"status": "failed", "reason": "missing_provider_signature"}

    headers = _SignatureHeadersProxy(sig)

    try:
        await process_order_created_webhook(
            session=session,
            store_identifier=store,
            raw_body=raw_body,
            headers=headers,
        )
    except PermissionError:
        await insert_domain_events_for_ingestion(
            session,
            webhook_ingestion_id=row.id,
            events=[
                (
                    "shopify.order_webhook.rejected",
                    row.workspace_id,
                    {"store_identifier": store, "reason": "invalid_hmac"},
                    f"reject:{row.id}:hmac",
                )
            ],
        )
        await session.commit()
        return {"status": "unauthorized", "reason": "invalid_hmac"}

    await insert_domain_events_for_ingestion(
        session,
        webhook_ingestion_id=row.id,
        events=[
            (
                "shopify.order_created.processed",
                row.workspace_id,
                {"store_identifier": store},
                f"shopify:{row.id}:{store}",
            )
        ],
    )
    await session.commit()
    return {"status": "ok", "store_identifier": store}
