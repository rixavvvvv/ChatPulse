import asyncio
import logging
import re

from redis.asyncio import Redis
from sqlalchemy import select

from app.core.config import get_settings
from app.db import AsyncSessionLocal, engine
from app.models.campaign import CampaignStatus
from app.models.campaign_contact import (
    CampaignContact,
    CampaignContactDeliveryStatus,
    CampaignFailureClassification,
)
from app.models.template import Template, TemplateStatus
from app.queue.base_tasks import (
    BaseCrashRecoveryTask,
    IdempotencyMixin,
    LongRunningTask,
    RetryStrategy,
)
from app.queue.celery_app import celery_app
from app.queue.registry import TASKS
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.campaign_recovery_service import (
    CampaignExecutionLeaseError,
    finalize_campaign_execution,
    initialize_campaign_execution,
    update_campaign_progress,
)
from app.services.campaign_service import get_campaign_by_id, set_campaign_status
from app.services.bulk_service import bulk_send_messages
from app.services.meta_template_params import build_numbered_template_parameters
from app.services.message_dispatch_service import send_template_with_tracking
from app.services.queue_dead_letter_service import persist_dead_letter_sync
from app.services.queue_monitoring_service import clear_task_checkpoints
from app.services.whatsapp_service import (
    ApiError,
    InvalidNumberError,
    RateLimitError,
)

from app.queue.rate_limit import (
    WorkspaceRateLimitExceeded as QueueWorkspaceRateLimitExceeded,
    enforce_workspace_rate_limit,
)

logger = logging.getLogger(__name__)
settings = get_settings()

retry_strategy = RetryStrategy(
    max_attempts=settings.queue_retry_max_attempts,
    base_delay_seconds=settings.queue_retry_base_delay_seconds,
)


def _inflight_key(idempotency_key: str) -> str:
    return f"queue:idempotency:inflight:{idempotency_key}"


def _sent_key(idempotency_key: str) -> str:
    return f"queue:idempotency:sent:{idempotency_key}"


async def _acquire_inflight(redis: Redis, idempotency_key: str) -> bool:
    return bool(
        await redis.set(
            _inflight_key(idempotency_key),
            "1",
            ex=settings.queue_inflight_ttl_seconds,
            nx=True,
        )
    )


async def _mark_sent(redis: Redis, idempotency_key: str) -> None:
    async with redis.pipeline(transaction=True) as pipe:
        pipe.set(
            _sent_key(idempotency_key),
            "1",
            ex=settings.queue_idempotency_ttl_seconds,
        )
        pipe.delete(_inflight_key(idempotency_key))
        await pipe.execute()


async def _release_inflight(redis: Redis, idempotency_key: str) -> None:
    await redis.delete(_inflight_key(idempotency_key))


async def _already_sent(redis: Redis, idempotency_key: str) -> bool:
    return bool(await redis.exists(_sent_key(idempotency_key)))


async def _dispose_engine() -> None:
    await engine.dispose()


def _run_with_engine_reset(coro):
    async def _runner():
        try:
            return await coro
        finally:
            # Dispose on the same loop as task execution to avoid cleanup against a closed loop.
            try:
                await _dispose_engine()
            except Exception as exc:  # pragma: no cover
                logger.warning(
                    "Failed to dispose SQLAlchemy engine after task run: %s", exc)

    return asyncio.run(_runner())


def _classify_error(exc: Exception) -> tuple[CampaignFailureClassification, bool]:
    if isinstance(exc, InvalidNumberError):
        return CampaignFailureClassification.invalid_number, False

    if isinstance(exc, (RateLimitError, QueueWorkspaceRateLimitExceeded)):
        return CampaignFailureClassification.rate_limit, True

    if isinstance(exc, ApiError):
        return CampaignFailureClassification.api_error, bool(exc.retryable)

    if isinstance(exc, BillingLimitExceeded):
        return CampaignFailureClassification.api_error, False

    return CampaignFailureClassification.api_error, True


def _retry_delay_seconds(attempt: int, suggested_delay: int | None = None) -> int:
    return retry_strategy.delay_seconds(attempt, suggested_delay)


async def _run_bulk_send(
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
    template_id: int | None = None,
) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        result = await bulk_send_messages(
            session=session,
            message_template=message_template,
            contact_ids=contact_ids,
            workspace_id=workspace_id,
            template_id=template_id,
        )
        return {
            "success_count": result.success_count,
            "failed_count": result.failed_count,
        }


class CampaignSendTask(LongRunningTask):
    """
    Campaign send task with crash recovery and idempotency.

    Late acknowledgment ensures the task is not lost if the worker crashes.
    Idempotency is handled at two levels:
    1. Redis sent key - prevents duplicate sends for same contact
    2. Delivery status check - skips already-sent contacts
    """

    abstract = True
    name = TASKS.campaign_send
    max_retries = 0  # Manual retry handling for campaign sends
    time_limit = 7200  # 2 hours max
    soft_time_limit = 6900  # 1 hour 55 min soft limit

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        """Handle campaign send failure - persist to DLQ."""
        if settings.queue_dlq_enabled:
            try:
                persist_dead_letter_sync(
                    task_name=self.name,
                    celery_task_id=task_id,
                    args=args,
                    kwargs=kwargs,
                    exception=exc,
                    einfo=einfo,
                    retries_at_failure=0,
                    max_retries=0,
                )
            except Exception as dlq_exc:
                logger.exception("DLQ persist failed: %s", dlq_exc)
        return super().on_failure(exc, task_id, args, kwargs, einfo)

    def on_success(self, retval, task_id, args, kwargs, einfo):
        """Clear checkpoints on successful completion."""
        try:
            clear_task_checkpoints(task_id)
        except Exception:  # pragma: no cover
            pass
        return super().on_success(retval, task_id, args, kwargs, einfo)


@celery_app.task(
    bind=True,
    base=CampaignSendTask,
    name=TASKS.campaign_send,
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_campaign_send_task(
    self,
    workspace_id: int,
    campaign_id: int,
) -> dict[str, int]:
    logger.info(
        "Campaign queue task started workspace_id=%s campaign_id=%s task_id=%s",
        workspace_id,
        campaign_id,
        self.request.id,
    )
    return _run_with_engine_reset(
        _run_campaign_send(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            task_id=self.request.id,
        )
    )


def run_campaign_send_inline(
    workspace_id: int,
    campaign_id: int,
) -> dict[str, int]:
    return _run_with_engine_reset(
        _run_campaign_send(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
        )
    )


async def _run_campaign_send(
    workspace_id: int,
    campaign_id: int,
    task_id: str | None = None,
) -> dict[str, int]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

    task_id = task_id or f"inline-{campaign_id}"
    execution_failed = False
    final_status = CampaignStatus.failed

    try:
        async with AsyncSessionLocal() as session:
            campaign = await get_campaign_by_id(
                session=session,
                workspace_id=workspace_id,
                campaign_id=campaign_id,
            )
            if not campaign:
                raise RuntimeError("Campaign not found")

            try:
                campaign = await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.running,
                )
            except ValueError as exc:
                raise RuntimeError(str(exc)) from exc

            audience_result = await session.execute(
                select(CampaignContact).where(
                    CampaignContact.workspace_id == workspace_id,
                    CampaignContact.campaign_id == campaign_id,
                )
            )
            audience = list(audience_result.scalars().all())

            template_result = await session.execute(
                select(Template).where(
                    Template.workspace_id == workspace_id,
                    Template.id == campaign.template_id,
                )
            )
            template = template_result.scalar_one_or_none()
            if not template:
                campaign = await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.failed,
                    success_count=0,
                    failed_count=0,
                    last_error="Template not found for campaign",
                )
                return {
                    "success_count": campaign.success_count,
                    "failed_count": campaign.failed_count,
                }

            if template.status != TemplateStatus.approved:
                campaign = await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.failed,
                    success_count=0,
                    failed_count=0,
                    last_error="Template must be approved before campaign send",
                )
                return {
                    "success_count": campaign.success_count,
                    "failed_count": campaign.failed_count,
                }

            if not template.meta_template_id:
                campaign = await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.failed,
                    success_count=0,
                    failed_count=0,
                    last_error="Template is not synced with Meta approval",
                )
                return {
                    "success_count": campaign.success_count,
                    "failed_count": campaign.failed_count,
                }

            if not audience:
                campaign = await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.failed,
                    success_count=0,
                    failed_count=0,
                    last_error="Campaign audience is empty",
                )
                return {
                    "success_count": campaign.success_count,
                    "failed_count": campaign.failed_count,
                }

            # Initialize campaign execution (acquire lease, heartbeat)
            try:
                await initialize_campaign_execution(session, redis, campaign, task_id)
            except CampaignExecutionLeaseError as exc:
                logger.warning(
                    "Campaign lease conflict campaign_id=%s reason=%s",
                    campaign_id, exc.reason
                )
                raise RuntimeError(
                    f"Campaign execution conflict: {exc.reason}. "
                    "Another worker may be processing this campaign."
                ) from exc

            success_count = 0
            failed_count = 0
            failure_reasons: list[str] = []
            processed = 0
            total = len(audience)

            for recipient in audience:
                processed += 1
                body_parameters = build_numbered_template_parameters(
                    text=template.body_text,
                    name=recipient.name,
                    phone=recipient.phone,
                )
                header_parameters = build_numbered_template_parameters(
                    text=template.header_content or "",
                    name=recipient.name,
                    phone=recipient.phone,
                )

                # IDEMPOTENCY CHECK - skip if already sent
                if await _already_sent(redis, recipient.idempotency_key):
                    recipient.delivery_status = CampaignContactDeliveryStatus.skipped
                    recipient.last_error = None
                    recipient.failure_classification = None
                    continue

                lock_acquired = await _acquire_inflight(redis, recipient.idempotency_key)
                if not lock_acquired:
                    recipient.delivery_status = CampaignContactDeliveryStatus.skipped
                    recipient.last_error = "Duplicate in-flight delivery prevented by idempotency lock"
                    recipient.failure_classification = CampaignFailureClassification.api_error
                    continue

                attempt = 0
                delivered = False

                while attempt < settings.queue_retry_max_attempts and not delivered:
                    attempt += 1
                    recipient.attempt_count = attempt

                    suggested_delay: int | None = None
                    try:
                        await ensure_workspace_can_send(
                            session=session,
                            workspace_id=workspace_id,
                            requested_count=1,
                        )
                        await enforce_workspace_rate_limit(redis, workspace_id)
                        dispatch = await send_template_with_tracking(
                            session=session,
                            workspace_id=workspace_id,
                            phone=recipient.phone,
                            template_name=template.name,
                            language=template.language,
                            body_parameters=body_parameters or None,
                            header_parameters=header_parameters or None,
                            campaign_id=campaign_id,
                            campaign_contact_id=recipient.id,
                            contact_id=recipient.source_contact_id,
                            max_attempts=1,
                        )
                        if dispatch.error_message:
                            raise RuntimeError(dispatch.error_message)
                        delivered = True
                        recipient.delivery_status = CampaignContactDeliveryStatus.sent
                        recipient.failure_classification = None
                        recipient.last_error = None
                        await _mark_sent(redis, recipient.idempotency_key)
                        success_count += 1
                    except Exception as exc:  # pragma: no cover
                        final_error = str(exc)
                        final_failure_classification, retryable = _classify_error(
                            exc)
                        recipient.failure_classification = final_failure_classification
                        recipient.last_error = final_error

                        if isinstance(exc, QueueWorkspaceRateLimitExceeded):
                            suggested_delay = exc.retry_after_seconds

                        if retryable and attempt < settings.queue_retry_max_attempts:
                            delay = _retry_delay_seconds(
                                attempt=attempt, suggested_delay=suggested_delay)
                            await asyncio.sleep(delay)
                            continue

                        recipient.delivery_status = CampaignContactDeliveryStatus.failed
                        failed_count += 1
                        failure_reasons.append(final_error)

                if not delivered:
                    await _release_inflight(redis, recipient.idempotency_key)

                campaign.success_count = success_count
                campaign.failed_count = failed_count
                await session.commit()

                # Save checkpoint every 100 contacts + update heartbeat
                if task_id and processed % 100 == 0:
                    try:
                        await update_campaign_progress(
                            session=session,
                            redis=redis,
                            campaign=campaign,
                            task_id=task_id,
                            processed=processed,
                            total=total,
                            success_count=success_count,
                            failed_count=failed_count,
                            checkpoint_index=recipient.id,
                        )
                    except Exception:  # pragma: no cover
                        pass

            # Determine final status
            if success_count > 0 and failed_count == 0:
                final_status = CampaignStatus.completed
            elif success_count > 0:
                final_status = CampaignStatus.completed
            else:
                final_status = CampaignStatus.failed

            await set_campaign_status(
                session=session,
                campaign=campaign,
                status=final_status,
                success_count=success_count,
                failed_count=failed_count,
                last_error=(failure_reasons[0] if failure_reasons else None),
            )

            return {
                "success_count": success_count,
                "failed_count": failed_count,
            }

    except Exception as exc:
        execution_failed = True
        logger.error(
            "Campaign execution failed campaign_id=%s error=%s",
            campaign_id, exc
        )
        raise

    finally:
        # Finalize campaign execution (release lease, clear heartbeat)
        if execution_failed:
            final_status = CampaignStatus.running  # Keep as running for recovery
        try:
            async with AsyncSessionLocal() as session:
                campaign = await session.get(Campaign, campaign_id)
                if campaign:
                    await finalize_campaign_execution(
                        session, redis, campaign, task_id, final_status
                    )
        except Exception as finalize_exc:
            logger.warning(
                "Failed to finalize campaign execution campaign_id=%s error=%s",
                campaign_id, finalize_exc
            )
        await redis.aclose()


class BulkSendTask(LongRunningTask):
    """Bulk send task with crash recovery support."""

    abstract = True
    name = TASKS.bulk_send_messages
    max_retries = 0
    time_limit = 3600  # 1 hour max
    soft_time_limit = 3300


@celery_app.task(
    bind=True,
    base=BulkSendTask,
    name=TASKS.bulk_send_messages,
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_bulk_send_task(
    self,
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
    template_id: int | None = None,
) -> dict[str, int]:
    logger.info(
        "Bulk send task started workspace_id=%s contact_count=%s task_id=%s",
        workspace_id,
        len(contact_ids),
        self.request.id,
    )
    return _run_with_engine_reset(
        _run_bulk_send(
            workspace_id=workspace_id,
            message_template=message_template,
            contact_ids=contact_ids,
            template_id=template_id,
        )
    )


class ContactImportTask(LongRunningTask):
    """Contact import task with crash recovery support."""

    abstract = True
    name = "contacts.import_job"
    max_retries = 0
    time_limit = 7200  # 2 hours
    soft_time_limit = 6900

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        if settings.queue_dlq_enabled:
            try:
                persist_dead_letter_sync(
                    task_name=self.name,
                    celery_task_id=task_id,
                    args=args,
                    kwargs=kwargs,
                    exception=exc,
                    einfo=einfo,
                    retries_at_failure=0,
                    max_retries=0,
                )
            except Exception as dlq_exc:
                logger.exception("DLQ persist failed: %s", dlq_exc)
        return super().on_failure(exc, task_id, args, kwargs, einfo)


@celery_app.task(
    bind=True,
    base=ContactImportTask,
    name="contacts.import_job",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_contact_import_job_task(
    self,
    workspace_id: int,
    job_id: int,
) -> dict:
    logger.info(
        "Contact import job task started workspace_id=%s job_id=%s task_id=%s",
        workspace_id,
        job_id,
        self.request.id,
    )
    return _run_with_engine_reset(
        _run_contact_import(
            workspace_id=workspace_id,
            job_id=job_id,
            task_id=self.request.id,
        )
    )


class SegmentMaterializeTask(LongRunningTask):
    """Segment materialization task with crash recovery support."""

    abstract = True
    name = "segments.materialize"
    max_retries = 0
    time_limit = 1800  # 30 minutes
    soft_time_limit = 1500


@celery_app.task(
    bind=True,
    base=SegmentMaterializeTask,
    name="segments.materialize",
    max_retries=0,
    acks_late=True,
    reject_on_worker_lost=True,
)
def process_segment_materialize_task(
    self,
    workspace_id: int,
    segment_id: int,
) -> dict:
    logger.info(
        "Segment materialize task started workspace_id=%s segment_id=%s task_id=%s",
        workspace_id,
        segment_id,
        self.request.id,
    )
    return _run_with_engine_reset(
        _run_segment_materialize(
            workspace_id=workspace_id,
            segment_id=segment_id,
            task_id=self.request.id,
        )
    )


async def _run_contact_import(workspace_id: int, job_id: int, task_id: str | None = None) -> dict:
    async with AsyncSessionLocal() as session:
        from app.services.contact_import_service import run_contact_import_job

        return await run_contact_import_job(
            session=session,
            workspace_id=workspace_id,
            job_id=job_id,
        )


async def _run_segment_materialize(
    workspace_id: int,
    segment_id: int,
    task_id: str | None = None,
) -> dict:
    async with AsyncSessionLocal() as session:
        from app.services.segment_service import get_segment, materialize_segment_membership

        segment = await get_segment(
            session=session, workspace_id=workspace_id, segment_id=segment_id
        )
        if not segment:
            return {"error": "segment_not_found"}
        count = await materialize_segment_membership(
            session=session, workspace_id=workspace_id, segment=segment
        )
        return {"status": "ok", "materialized_count": count}
