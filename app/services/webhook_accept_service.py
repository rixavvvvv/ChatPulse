from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.webhook_ingestion import WebhookSource
from app.services.ecommerce_store_service import get_store_by_identifier
from app.services.order_webhook_service import (
    _first_signature_header,
    _plaintext_secret,
    verify_hmac_sha256_base64,
)
from app.services.webhook_idempotency_service import (
    check_webhook_idempotency,
    extract_provider_event_id_from_payload,
    get_idempotency_service,
)
from app.services.webhook_ingestion_service import (
    create_webhook_ingestion,
    enqueue_webhook_dispatch_task,
    find_recent_duplicate_ingestion,
    mark_ingestion_completed,
    mark_ingestion_queued,
)
from app.services.webhook_verification import (
    summarize_headers,
    webhook_dedupe_key,
)

logger = logging.getLogger(__name__)


async def accept_meta_whatsapp_webhook(
    session: AsyncSession,
    *,
    raw_body: bytes,
    payload: dict[str, Any],
    request_headers: Any,
) -> dict[str, Any]:
    source = WebhookSource.meta_whatsapp.value

    # PROVIDER-LEVEL IDEMPOTENCY CHECK
    # Uses Redis SETNX for fast dedupe, PostgreSQL unique constraint as authoritative
    result, provider_event_id = await check_webhook_idempotency(
        session=session,
        source=source,
        raw_body=raw_body,
        payload=payload,
    )

    if result.is_duplicate:
        await session.commit()
        return {
            "status": "ok",
            "deduplicated": True,
            "ingestion_id": result.existing_ingestion_id or result.new_ingestion_id,
            "reason": result.reason,
        }

    # No deduplication - create new ingestion with provider_event_id
    dedupe_key = webhook_dedupe_key(source=source, raw_body=raw_body, store_fragment=None)
    row = await create_webhook_ingestion(
        session,
        source=source,
        raw_body=raw_body,
        payload_json=payload,
        store_identifier=None,
        verification_passed=True,
        verification_error=None,
        headers_meta=summarize_headers(request_headers),
        persist_raw_body=False,
        provider_signature=None,
        provider_event_id=provider_event_id,
    )
    task_id = enqueue_webhook_dispatch_task(row.id)
    await mark_ingestion_queued(session, row, celery_task_id=task_id)
    await session.commit()
    return {
        "status": "accepted",
        "deduplicated": False,
        "ingestion_id": row.id,
        "celery_task_id": task_id,
    }


async def accept_shopify_order_created_webhook(
    session: AsyncSession,
    *,
    store_identifier: str,
    raw_body: bytes,
    request_headers: Any,
) -> dict[str, Any]:
    connection = await get_store_by_identifier(
        session, store_identifier=store_identifier
    )
    if not connection:
        logger.warning(
            "Shopify order webhook: unknown store_identifier=%s", store_identifier
        )
        return {"status": "ok", "ingestion_id": None, "note": "unknown_store"}

    plain_secret = _plaintext_secret(connection)
    sig = _first_signature_header(request_headers)
    if not sig or not verify_hmac_sha256_base64(plain_secret, raw_body, sig):
        raise PermissionError("Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid JSON payload") from exc
    if not isinstance(payload, dict):
        raise ValueError("Webhook payload must be a JSON object")

    source = WebhookSource.shopify_orders.value

    # PROVIDER-LEVEL IDEMPOTENCY CHECK
    # Uses Redis SETNX for fast dedupe, PostgreSQL unique constraint as authoritative
    result, provider_event_id = await check_webhook_idempotency(
        session=session,
        source=source,
        raw_body=raw_body,
        payload=payload,
    )

    if result.is_duplicate:
        await session.commit()
        return {
            "status": "ok",
            "deduplicated": True,
            "ingestion_id": result.existing_ingestion_id or result.new_ingestion_id,
            "reason": result.reason,
        }

    # No deduplication - create new ingestion with provider_event_id
    dedupe_key = webhook_dedupe_key(
        source=source, raw_body=raw_body, store_fragment=store_identifier
    )
    row = await create_webhook_ingestion(
        session,
        source=source,
        raw_body=raw_body,
        payload_json=payload,
        store_identifier=store_identifier,
        verification_passed=True,
        verification_error=None,
        headers_meta=summarize_headers(request_headers),
        workspace_id=connection.workspace_id,
        persist_raw_body=True,
        provider_signature=sig.strip(),
        provider_event_id=provider_event_id,
    )
    task_id = enqueue_webhook_dispatch_task(row.id)
    await mark_ingestion_queued(session, row, celery_task_id=task_id)
    await session.commit()
    return {
        "status": "accepted",
        "deduplicated": False,
        "ingestion_id": row.id,
        "celery_task_id": task_id,
    }
