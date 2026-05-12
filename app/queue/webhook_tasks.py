from __future__ import annotations

import asyncio
import logging

from celery import Task
from celery.exceptions import Retry
from sqlalchemy.exc import OperationalError

from app.core.config import get_settings
from app.db import AsyncSessionLocal, engine
from app.models.webhook_ingestion import WebhookIngestionStatus
from app.queue.base_tasks import (
    BaseCrashRecoveryTask,
    FastIOTask,
    IdempotencyMixin,
)
from app.queue.celery_app import celery_app
from app.queue.registry import TASKS
from app.services.queue_dead_letter_service import persist_dead_letter_sync
from app.services.queue_monitoring_service import clear_task_checkpoints
from app.services.webhook_dispatcher_service import dispatch_webhook_ingestion
from app.services.webhook_idempotency_service import get_idempotency_service
from app.services.webhook_ingestion_service import get_ingestion_by_id

logger = logging.getLogger(__name__)
settings = get_settings()


async def _dispose_engine() -> None:
    await engine.dispose()


def _run_with_engine_reset(coro):
    async def _runner():
        try:
            return await coro
        finally:
            try:
                await _dispose_engine()
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Failed to dispose SQLAlchemy engine after webhook task: %s", exc
                )

    return asyncio.run(_runner())


class WebhookRetryTask(FastIOTask):
    """
    Webhook dispatch task with crash recovery and idempotency.

    Features:
    - Late acknowledgment for message safety
    - Automatic retry on transient DB/broker failures
    - DLQ persistence when retries exhausted
    - Idempotency check before processing
    """

    abstract = True
    autoretry_for = (OperationalError, ConnectionError, OSError, TimeoutError)
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True
    acks_late = True
    reject_on_worker_lost = True
    time_limit = 60  # 1 minute hard limit
    soft_time_limit = 45  # 45 second soft limit

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle task failure - persist to DLQ if retries exhausted."""
        if isinstance(exc, Retry):
            return super().on_failure(exc, task_id, args, kwargs, einfo)

        if settings.queue_dlq_enabled and self.max_retries > 0 and self.request.retries >= self.max_retries:
            try:
                persist_dead_letter_sync(
                    task_name=self.name,
                    celery_task_id=task_id,
                    args=args,
                    kwargs=kwargs,
                    exception=exc,
                    einfo=einfo,
                    retries_at_failure=self.request.retries,
                    max_retries=self.max_retries,
                )
            except Exception as dlq_exc:  # pragma: no cover
                logger.exception("DLQ persist failed: %s", dlq_exc)
        return super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs, einfo):
        """Clear checkpoints on successful completion."""
        try:
            clear_task_checkpoints(task_id)
        except Exception:  # pragma: no cover
            pass
        return super().on_success(retval, task_id, args, kwargs, einfo)


async def _run_webhook_dispatch(ingestion_id: int) -> dict:
    """Execute webhook dispatch with provider-level idempotency check."""
    async with AsyncSessionLocal() as session:
        row = await get_ingestion_by_id(session, ingestion_id)
        if not row:
            return {"error": "ingestion_not_found", "ingestion_id": ingestion_id}

        # PROVIDER-LEVEL IDEMPOTENCY CHECK
        # Use the provider_event_id from the ingestion record
        # This ensures we don't process the same webhook event twice
        if row.provider_event_id:
            service = get_idempotency_service()
            result = await service.check_and_acquire(
                session=session,
                source=row.source,
                provider_event_id=row.provider_event_id,
                dedupe_key=row.dedupe_key,
            )
            if result.is_duplicate and not result.should_process:
                return {
                    "status": "duplicate_skipped",
                    "ingestion_id": ingestion_id,
                    "existing_ingestion_id": result.existing_ingestion_id,
                    "reason": result.reason,
                }

        # Skip if already completed - check authoritative DB status
        if row.processing_status == WebhookIngestionStatus.completed.value:
            return {
                "status": "already_completed",
                "ingestion_id": ingestion_id,
                "dispatch_result": row.dispatch_result,
            }

        if row.processing_status not in (
            WebhookIngestionStatus.queued.value,
            WebhookIngestionStatus.processing.value,
            WebhookIngestionStatus.received.value,
            WebhookIngestionStatus.verified.value,
        ):
            return {
                "error": "invalid_ingestion_state",
                "ingestion_id": ingestion_id,
                "processing_status": row.processing_status,
            }

        return await dispatch_webhook_ingestion(session, row)


@celery_app.task(
    bind=True,
    base=WebhookRetryTask,
    name=TASKS.webhook_process_ingestion,
    max_retries=settings.webhook_dispatch_max_retries,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_webhook_ingestion(self, ingestion_id: int) -> dict:
    """
    Process a webhook ingestion with crash recovery.

    Late acknowledgment ensures the webhook is requeued if this worker crashes.
    Idempotency check ensures already-processed webhooks are skipped.
    """
    logger.info(
        "Webhook dispatch task ingestion_id=%s task_id=%s attempt=%s",
        ingestion_id,
        self.request.id,
        self.request.retries + 1,
    )

    # Use idempotency key based on ingestion_id + status
    # This allows retry even if previous attempt failed
    key_suffix = f"ingestion:{ingestion_id}:attempt:{self.request.retries}"

    # Execute the task with async Redis operations
    result = _run_webhook_dispatch_with_redis(
        ingestion_id, key_suffix, self.name, self.request.retries
    )

    return result


def _run_webhook_dispatch_with_redis(
    ingestion_id: int, key_suffix: str, task_name: str, retries: int
) -> dict:
    """Execute webhook dispatch with task-level Redis idempotency."""
    import asyncio
    from redis.asyncio import Redis

    async def _async_run():
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            # Check if this specific attempt already completed
            already_done = await IdempotencyMixin.is_completed(
                redis, key_suffix, task_name
            )
            if already_done:
                logger.info(
                    "Webhook ingestion already processed ingestion_id=%s attempt=%s",
                    ingestion_id,
                    retries,
                )
                return {
                    "status": "already_completed",
                    "ingestion_id": ingestion_id,
                }

            # Execute the task
            result = _run_with_engine_reset(_run_webhook_dispatch(ingestion_id))

            # Mark this attempt as completed
            await IdempotencyMixin.mark_completed(
                redis, key_suffix, task_name,
                ttl_seconds=settings.queue_idempotency_ttl_seconds,
            )

            return result
        finally:
            await redis.aclose()

    return asyncio.run(_async_run())

