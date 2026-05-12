"""
Provider-level idempotency service for webhooks.

This module implements dual-layer idempotency:
1. Redis (fast path): SETNX for in-flight dedupe with atomic operations
2. PostgreSQL (authoritative): UNIQUE constraint on (source, provider_event_id)

Idempotency Keys
----------------
Each webhook source has a provider-specific idempotency key:

Meta WhatsApp:
  - Delivery/read/failed status: Extract wamid from payload.id
  - Incoming messages: Extract message ID from message.id
  - Value: The Meta message ID (wamid)

Shopify:
  - Order created: Extract order_id from payload.id
  - Value: The Shopify order/checkout ID

If provider doesn't provide stable ID, fall back to dedupe_key hash.

Exactly-Once vs At-Least-Once
------------------------------
This implementation provides "effectively exactly-once" delivery:
- Duplicate webhook delivery: Skipped at ingestion (Redis SETNX)
- Worker crash mid-processing: Skipped at dispatch (DB status check)
- Replay after failure: Idempotency key re-checked before execution

The "effectively" qualifier is because:
- Some operations are inherently non-idempotent (e.g., order confirmation emails)
- We handle this at the business logic layer (e.g., order status updates are idempotent)
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.webhook_ingestion import (
    WebhookIngestion,
    WebhookIngestionStatus,
    WebhookSource,
)

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True)
class IdempotencyResult:
    """Result of an idempotency check."""

    is_duplicate: bool
    existing_ingestion_id: int | None
    new_ingestion_id: int | None
    should_process: bool
    reason: str


# Redis key patterns for idempotency
_IDEMPOTENCY_KEY_PREFIX = "webhook:idempotency"
_PROCESSING_KEY_PREFIX = "webhook:processing"
_COMPLETED_KEY_PREFIX = "webhook:completed"


def _idempotency_key(source: str, provider_event_id: str) -> str:
    """Generate Redis key for idempotency check."""
    return f"{_IDEMPOTENCY_KEY_PREFIX}:{source}:{provider_event_id}"


def _processing_key(source: str, provider_event_id: str) -> str:
    """Generate Redis key for in-flight processing."""
    return f"{_PROCESSING_KEY_PREFIX}:{source}:{provider_event_id}"


def _completed_key(source: str, provider_event_id: str) -> str:
    """Generate Redis key for completed status."""
    return f"{_COMPLETED_KEY_PREFIX}:{source}:{provider_event_id}"


def _extract_provider_event_id(payload: dict[str, Any], source: str) -> str:
    """
    Extract the provider-specific event ID from webhook payload.

    This ID uniquely identifies the event from the provider's perspective
    and is used for idempotency checks.
    """
    if source == WebhookSource.meta_whatsapp.value:
        return _extract_meta_event_id(payload)
    elif source == WebhookSource.shopify_orders.value:
        return _extract_shopify_event_id(payload)
    else:
        raise ValueError(f"Unknown webhook source: {source}")


def _extract_meta_event_id(payload: dict[str, Any]) -> str:
    """
    Extract Meta WhatsApp event ID from payload.

    Meta webhooks contain different structures:
    - Delivery receipts: entry[].changes[].value.statuses[].id (wamid)
    - Read receipts: entry[].changes[].value.statuses[].id (wamid)
    - Incoming messages: entry[].changes[].value.messages[].id

    Returns the wamid/message ID, or raises ValueError.
    """
    try:
        entries = payload.get("entry", [])
        if not isinstance(entries, list):
            raise ValueError("Meta payload missing entry list")

        for entry in entries:
            if not isinstance(entry, dict):
                continue

            # Check for status updates (delivered, read, failed)
            changes = entry.get("changes", [])
            if isinstance(changes, list):
                for change in changes:
                    if not isinstance(change, dict):
                        continue

                    value = change.get("value", {})
                    if not isinstance(value, dict):
                        continue

                    # Status updates (delivery, read, failed)
                    statuses = value.get("statuses", [])
                    if isinstance(statuses, list) and statuses:
                        for status in statuses:
                            if isinstance(status, dict):
                                msg_id = status.get("id")
                                if msg_id and isinstance(msg_id, str):
                                    return msg_id

                    # Incoming messages
                    messages = value.get("messages", [])
                    if isinstance(messages, list) and messages:
                        for msg in messages:
                            if isinstance(msg, dict):
                                msg_id = msg.get("id")
                                if msg_id and isinstance(msg_id, str):
                                    return msg_id

        raise ValueError("No Meta event ID found in payload")

    except Exception as exc:
        raise ValueError(f"Failed to extract Meta event ID: {exc}") from exc


def _extract_shopify_event_id(payload: dict[str, Any]) -> str:
    """
    Extract Shopify event ID from payload.

    Shopify order webhooks contain:
    - Order created: payload.id (order ID)

    Returns the Shopify order ID, or raises ValueError.
    """
    try:
        order_id = payload.get("id")
        if not order_id:
            raise ValueError("Shopify payload missing id field")

        # Shopify order IDs can be integers or strings
        return str(order_id)

    except Exception as exc:
        raise ValueError(f"Failed to extract Shopify event ID: {exc}") from exc


def _extract_id_from_payload(source: str, raw_body: bytes) -> str:
    """
    Fallback: Generate stable ID from payload content.

    Used when provider doesn't provide a stable event ID.
    Uses SHA256 of raw body for deterministic generation.
    """
    h = hashlib.sha256()
    h.update(raw_body)
    return f"sha256:{h.hexdigest()[:32]}"


class WebhookIdempotencyService:
    """
    Dual-layer idempotency service for webhook processing.

    Layer 1 - Redis (fast path):
    - SETNX for immediate dedupe of concurrent requests
    - Processing lock for in-flight webhooks
    - Completed flag for fast lookup

    Layer 2 - PostgreSQL (authoritative):
    - UNIQUE constraint on (source, provider_event_id)
    - Handles race conditions Redis can't catch
    - Authoritative record for replay scenarios
    """

    def __init__(self, redis_url: str | None = None, ttl_seconds: int | None = None):
        self.redis_url = redis_url or settings.redis_url
        self.ttl_seconds = ttl_seconds or settings.webhook_dedupe_ttl_seconds

    async def _get_redis(self) -> Redis:
        """Get async Redis connection."""
        return Redis.from_url(self.redis_url, decode_responses=True)

    async def check_and_acquire(
        self,
        session: AsyncSession,
        *,
        source: str,
        provider_event_id: str,
        dedupe_key: str,
    ) -> IdempotencyResult:
        """
        Check idempotency and acquire lock if not duplicate.

        This is the main entry point for idempotency checking.
        Uses Redis for fast path, then PostgreSQL for authoritative check.

        Returns:
            IdempotencyResult with is_duplicate=True if already processed
            IdempotencyResult with should_process=True if should proceed
        """
        redis = await self._get_redis()
        try:
            return await self._check_and_acquire_with_redis(
                redis, session, source, provider_event_id, dedupe_key
            )
        finally:
            await redis.aclose()

    async def _check_and_acquire_with_redis(
        self,
        redis: Redis,
        session: AsyncSession,
        source: str,
        provider_event_id: str,
        dedupe_key: str,
    ) -> IdempotencyResult:
        """
        Check idempotency with Redis fast path.

        Uses Redis SETNX for atomic lock acquisition.
        """
        idempotency_key = _idempotency_key(source, provider_event_id)

        # Fast path: Check if already completed in Redis
        completed = await redis.get(_completed_key(source, provider_event_id))
        if completed:
            ingestion_id = int(completed)
            return IdempotencyResult(
                is_duplicate=True,
                existing_ingestion_id=ingestion_id,
                new_ingestion_id=None,
                should_process=False,
                reason="Already completed (Redis cache)",
            )

        # Try to acquire idempotency lock
        # NX = only if not exists (atomic SETNX)
        # EX = expire after TTL
        acquired = await redis.set(
            idempotency_key,
            "processing",
            ex=self.ttl_seconds,
            nx=True,
        )

        if not acquired:
            # Another instance is processing this webhook
            # Check if it's completed or still processing
            existing = await redis.get(idempotency_key)
            if existing == "completed":
                return IdempotencyResult(
                    is_duplicate=True,
                    existing_ingestion_id=None,  # Redis doesn't store ID
                    new_ingestion_id=None,
                    should_process=False,
                    reason="Processing in progress by another worker",
                )
            elif existing:
                return IdempotencyResult(
                    is_duplicate=True,
                    existing_ingestion_id=None,
                    new_ingestion_id=None,
                    should_process=False,
                    reason="In-flight processing detected",
                )

        # No Redis result - need to check PostgreSQL
        return await self._check_postgresql(session, source, provider_event_id, dedupe_key)

    async def _check_postgresql(
        self,
        session: AsyncSession,
        source: str,
        provider_event_id: str,
        dedupe_key: str,
    ) -> IdempotencyResult:
        """
        Check PostgreSQL for existing ingestion with provider_event_id.

        This is the authoritative check that handles:
        - Worker restarts (Redis cleared but DB record exists)
        - Race conditions between workers
        - Replay scenarios
        """
        stmt = select(WebhookIngestion).where(
            WebhookIngestion.source == source,
            WebhookIngestion.provider_event_id == provider_event_id,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing:
            # Found existing ingestion
            return IdempotencyResult(
                is_duplicate=True,
                existing_ingestion_id=existing.id,
                new_ingestion_id=None,
                should_process=existing.processing_status
                in (
                    WebhookIngestionStatus.queued.value,
                    WebhookIngestionStatus.processing.value,
                ),
                reason=f"Existing ingestion: {existing.processing_status}",
            )

        # No existing record - create new ingestion
        return await self._create_ingestion(session, source, provider_event_id, dedupe_key)

    async def _create_ingestion(
        self,
        session: AsyncSession,
        source: str,
        provider_event_id: str,
        dedupe_key: str,
    ) -> IdempotencyResult:
        """Create new ingestion with provider_event_id."""
        try:
            row = WebhookIngestion(
                source=source,
                provider_event_id=provider_event_id,
                dedupe_key=dedupe_key,
                processing_status=WebhookIngestionStatus.received.value,
            )
            session.add(row)
            await session.flush()

            return IdempotencyResult(
                is_duplicate=False,
                existing_ingestion_id=None,
                new_ingestion_id=row.id,
                should_process=True,
                reason="New ingestion created",
            )

        except IntegrityError:
            # Unique constraint violation - another request beat us
            await session.rollback()
            return IdempotencyResult(
                is_duplicate=True,
                existing_ingestion_id=None,
                new_ingestion_id=None,
                should_process=False,
                reason="Duplicate detected (unique constraint)",
            )

    async def mark_processing(
        self,
        source: str,
        provider_event_id: str,
        ingestion_id: int,
    ) -> None:
        """Mark webhook as actively processing."""
        redis = await self._get_redis()
        try:
            key = _processing_key(source, provider_event_id)
            idempotency_key = _idempotency_key(source, provider_event_id)

            # Update Redis with processing state
            await redis.set(key, str(ingestion_id), ex=self.ttl_seconds)
            await redis.set(
                idempotency_key,
                f"processing:{ingestion_id}",
                ex=self.ttl_seconds,
            )
        finally:
            await redis.aclose()

    async def mark_completed(
        self,
        source: str,
        provider_event_id: str,
        ingestion_id: int,
    ) -> None:
        """Mark webhook as completed."""
        redis = await self._get_redis()
        try:
            # Update keys to completed state
            completed_key = _completed_key(source, provider_event_id)
            idempotency_key = _idempotency_key(source, provider_event_id)
            processing_key = _processing_key(source, provider_event_id)

            # Use pipeline for atomic update
            async with redis.pipeline(transaction=True) as pipe:
                pipe.set(completed_key, str(ingestion_id), ex=self.ttl_seconds)
                pipe.delete(processing_key)
                pipe.set(idempotency_key, f"completed:{ingestion_id}", ex=self.ttl_seconds)
                await pipe.execute()
        finally:
            await redis.aclose()

    async def release_lock(
        self,
        source: str,
        provider_event_id: str,
    ) -> None:
        """
        Release idempotency lock (for retry scenarios).

        Call this if webhook processing fails and should allow retry.
        """
        redis = await self._get_redis()
        try:
            key = _idempotency_key(source, provider_event_id)
            processing_key = _processing_key(source, provider_event_id)
            await redis.delete(key, processing_key)
        finally:
            await redis.aclose()


def get_idempotency_service() -> WebhookIdempotencyService:
    """Get singleton idempotency service instance."""
    return WebhookIdempotencyService()


async def check_webhook_idempotency(
    session: AsyncSession,
    source: str,
    raw_body: bytes,
    payload: dict[str, Any],
) -> tuple[IdempotencyResult, str]:
    """
    High-level idempotency check for webhooks.

    Args:
        session: Database session
        source: Webhook source (e.g., "meta_whatsapp")
        raw_body: Raw webhook body bytes
        payload: Parsed JSON payload

    Returns:
        Tuple of (IdempotencyResult, provider_event_id)
    """
    service = get_idempotency_service()

    # Extract provider event ID
    try:
        provider_event_id = _extract_provider_event_id(payload, source)
    except ValueError:
        # Fallback to dedupe key if extraction fails
        provider_event_id = _extract_id_from_payload(source, raw_body)

    # Generate dedupe key for short-window dedupe
    dedupe_key = hashlib.sha256(raw_body).hexdigest()

    # Check and acquire idempotency
    result = await service.check_and_acquire(
        session=session,
        source=source,
        provider_event_id=provider_event_id,
        dedupe_key=dedupe_key,
    )

    return result, provider_event_id


def extract_provider_event_id_from_payload(
    source: str,
    payload: dict[str, Any],
) -> str | None:
    """
    Extract provider event ID from payload without raising.

    Returns None if extraction fails.
    """
    try:
        return _extract_provider_event_id(payload, source)
    except ValueError:
        return None
