import asyncio
import logging
import math
import re
import time
from uuid import uuid4

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
from app.models.message_event import MessageEventStatus
from app.models.template import Template, TemplateStatus
from app.queue.celery_app import celery_app
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.campaign_service import get_campaign_by_id, set_campaign_status
from app.services.bulk_service import bulk_send_messages
from app.services.message_event_service import record_message_event
from app.services.webhook_service import register_sent_message
from app.services.whatsapp_service import (
    ApiError,
    InvalidNumberError,
    RateLimitError,
    send_whatsapp_template_message,
)

logger = logging.getLogger(__name__)
NUMBER_VARIABLE_PATTERN = re.compile(r"\{\{\s*(\d+)\s*\}\}")
settings = get_settings()


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
                logger.warning("Failed to dispose SQLAlchemy engine after task run: %s", exc)

    return asyncio.run(_runner())


class WorkspaceRateLimitExceeded(Exception):
    def __init__(self, retry_after_seconds: int):
        super().__init__(
            f"Workspace rate limit exceeded, retry after {retry_after_seconds}s")
        self.retry_after_seconds = retry_after_seconds


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


async def _enforce_workspace_rate_limit(redis: Redis, workspace_id: int) -> None:
    now_ms = int(time.time() * 1000)
    window_ms = settings.queue_workspace_rate_limit_window_seconds * 1000
    key = f"queue:rate_limit:{workspace_id}"

    async with redis.pipeline(transaction=True) as pipe:
        pipe.zremrangebyscore(key, 0, now_ms - window_ms)
        pipe.zcard(key)
        cleaned_count = await pipe.execute()

    current_count = int(cleaned_count[1])
    if current_count >= settings.queue_workspace_rate_limit_count:
        oldest = await redis.zrange(key, 0, 0, withscores=True)
        retry_after = 1
        if oldest:
            oldest_timestamp = int(oldest[0][1])
            retry_after = max(
                1,
                math.ceil((oldest_timestamp + window_ms - now_ms) / 1000),
            )
        raise WorkspaceRateLimitExceeded(retry_after_seconds=retry_after)

    await redis.zadd(key, {f"{now_ms}-{uuid4().hex}": now_ms})
    await redis.expire(key, settings.queue_workspace_rate_limit_window_seconds * 2)


def _classify_error(exc: Exception) -> tuple[CampaignFailureClassification, bool]:
    if isinstance(exc, InvalidNumberError):
        return CampaignFailureClassification.invalid_number, False

    if isinstance(exc, (RateLimitError, WorkspaceRateLimitExceeded)):
        return CampaignFailureClassification.rate_limit, True

    if isinstance(exc, ApiError):
        return CampaignFailureClassification.api_error, bool(exc.retryable)

    if isinstance(exc, BillingLimitExceeded):
        return CampaignFailureClassification.api_error, False

    return CampaignFailureClassification.api_error, True


def _retry_delay_seconds(attempt: int, suggested_delay: int | None = None) -> int:
    exponential = settings.queue_retry_base_delay_seconds * \
        (2 ** max(0, attempt - 1))
    if suggested_delay is None:
        return exponential
    return max(exponential, suggested_delay)


async def _run_bulk_send(
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        result = await bulk_send_messages(
            session=session,
            message_template=message_template,
            contact_ids=contact_ids,
            workspace_id=workspace_id,
        )
        return {
            "success_count": result.success_count,
            "failed_count": result.failed_count,
        }


@celery_app.task(name="bulk.send_messages")
def process_bulk_send_task(
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
) -> dict[str, int]:
    logger.info(
        "Queue task started workspace_id=%s contact_count=%s",
        workspace_id,
        len(contact_ids),
    )
    return _run_with_engine_reset(
        _run_bulk_send(
            workspace_id=workspace_id,
            message_template=message_template,
            contact_ids=contact_ids,
        )
    )


def _extract_number_placeholders(text: str) -> list[int]:
    numbers: list[int] = []
    seen: set[int] = set()
    for match in NUMBER_VARIABLE_PATTERN.finditer(text):
        number = int(match.group(1))
        if number in seen:
            continue
        seen.add(number)
        numbers.append(number)
    numbers.sort()
    return numbers


def _build_template_parameters(text: str, name: str, phone: str) -> list[str]:
    placeholders = _extract_number_placeholders(text)
    if not placeholders:
        return []

    values: list[str] = []
    for index in placeholders:
        if index == 1:
            values.append(name or "Customer")
        elif index == 2:
            values.append(phone)
        else:
            values.append(f"Value {index}")
    return values


async def _run_campaign_send(
    workspace_id: int,
    campaign_id: int,
) -> dict[str, int]:
    redis = Redis.from_url(settings.redis_url, decode_responses=True)

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

            success_count = 0
            failed_count = 0
            failure_reasons: list[str] = []

            for recipient in audience:
                body_parameters = _build_template_parameters(
                    text=template.body_text,
                    name=recipient.name,
                    phone=recipient.phone,
                )
                header_parameters = _build_template_parameters(
                    text=template.header_content or "",
                    name=recipient.name,
                    phone=recipient.phone,
                )

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
                        await _enforce_workspace_rate_limit(redis, workspace_id)
                        send_result = await send_whatsapp_template_message(
                            workspace_id=workspace_id,
                            phone=recipient.phone,
                            template_name=template.name,
                            language=template.language,
                            body_parameters=body_parameters or None,
                            header_parameters=header_parameters or None,
                        )
                        provider_message_id = send_result.get("message_id")
                        if isinstance(provider_message_id, str) and provider_message_id.strip():
                            await register_sent_message(
                                session=session,
                                workspace_id=workspace_id,
                                provider_message_id=provider_message_id,
                                recipient_phone=recipient.phone,
                                campaign_id=campaign_id,
                                campaign_contact_id=recipient.id,
                            )
                            await record_message_event(
                                session=session,
                                workspace_id=workspace_id,
                                campaign_id=campaign_id,
                                contact_id=recipient.source_contact_id,
                                status=MessageEventStatus.sent,
                            )
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

                        if isinstance(exc, WorkspaceRateLimitExceeded):
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

            if success_count > 0:
                await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.completed,
                    success_count=success_count,
                    failed_count=failed_count,
                    last_error=(failure_reasons[0]
                                if failure_reasons else None),
                )
            else:
                await set_campaign_status(
                    session=session,
                    campaign=campaign,
                    status=CampaignStatus.failed,
                    success_count=success_count,
                    failed_count=failed_count,
                    last_error=(
                        failure_reasons[0] if failure_reasons else "All sends failed"),
                )

            return {
                "success_count": success_count,
                "failed_count": failed_count,
            }
    finally:
        await redis.aclose()


@celery_app.task(name="campaign.send")
def process_campaign_send_task(
    workspace_id: int,
    campaign_id: int,
) -> dict[str, int]:
    logger.info(
        "Campaign queue task started workspace_id=%s campaign_id=%s",
        workspace_id,
        campaign_id,
    )
    return _run_with_engine_reset(
        _run_campaign_send(
            workspace_id=workspace_id,
            campaign_id=campaign_id,
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
