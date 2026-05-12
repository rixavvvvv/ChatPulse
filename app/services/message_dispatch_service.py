from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.message_event import MessageEventStatus
from app.services.message_event_service import record_message_event
from app.services.webhook_service import register_sent_message
from app.services.whatsapp_service import ApiError, InvalidNumberError, RateLimitError, send_whatsapp_template_message

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass(frozen=True, slots=True)
class DispatchResult:
    provider_message_id: str | None
    retryable: bool
    error_message: str | None
    failure_classification: str | None


def _classify_send_error(exc: Exception) -> tuple[str, bool]:
    if isinstance(exc, InvalidNumberError):
        return ("invalid_number", False)
    if isinstance(exc, RateLimitError):
        return ("rate_limit", True)
    if isinstance(exc, ApiError):
        return ("api_error", bool(exc.retryable))
    return ("api_error", True)


def _retry_delay_seconds(attempt: int, base_delay: int) -> int:
    return base_delay * (2 ** max(0, attempt - 1))


async def send_template_with_tracking(
    session: AsyncSession,
    *,
    workspace_id: int,
    phone: str,
    template_name: str,
    language: str,
    body_parameters: list[str] | None,
    header_parameters: list[str] | None,
    campaign_id: int | None,
    campaign_contact_id: int | None,
    contact_id: int | None,
    max_attempts: int | None = None,
) -> DispatchResult:
    attempts = max_attempts if max_attempts is not None else settings.queue_retry_max_attempts
    last_error: str | None = None
    last_classification: str | None = None
    retryable = True

    for attempt in range(1, max(1, attempts) + 1):
        try:
            send_result = await send_whatsapp_template_message(
                workspace_id=workspace_id,
                phone=phone,
                template_name=template_name,
                language=language,
                body_parameters=body_parameters or None,
                header_parameters=header_parameters or None,
            )
            provider_message_id = send_result.get("message_id")
            provider_message_id_str = (
                provider_message_id.strip()
                if isinstance(provider_message_id, str) and provider_message_id.strip()
                else None
            )
            if provider_message_id_str:
                await register_sent_message(
                    session=session,
                    workspace_id=workspace_id,
                    provider_message_id=provider_message_id_str,
                    recipient_phone=phone,
                    campaign_id=campaign_id,
                    campaign_contact_id=campaign_contact_id,
                )
            await record_message_event(
                session=session,
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                contact_id=contact_id,
                status=MessageEventStatus.sent,
            )
            await session.commit()
            return DispatchResult(
                provider_message_id=provider_message_id_str,
                retryable=False,
                error_message=None,
                failure_classification=None,
            )
        except Exception as exc:  # pragma: no cover
            last_error = str(exc)
            last_classification, retryable = _classify_send_error(exc)
            if retryable and attempt < attempts:
                await asyncio.sleep(_retry_delay_seconds(attempt, settings.queue_retry_base_delay_seconds))
                continue
            return DispatchResult(
                provider_message_id=None,
                retryable=retryable,
                error_message=last_error,
                failure_classification=last_classification,
            )

    return DispatchResult(
        provider_message_id=None,
        retryable=retryable,
        error_message=last_error or "Send failed",
        failure_classification=last_classification or "api_error",
    )

