import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.message_event import MessageEventStatus
from app.models.template import TemplateStatus
from app.schemas.bulk import BulkDeliveryResult, BulkSendResponse
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.meta_template_params import build_numbered_template_parameters
from app.services.message_event_service import record_message_event
from app.services.template_service import get_template_by_id
from app.services.webhook_service import register_sent_message
from app.services.whatsapp_service import (
    ApiError,
    InvalidNumberError,
    RateLimitError,
    send_whatsapp_message,
    send_whatsapp_template_message,
)

logger = logging.getLogger(__name__)
VARIABLE_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")


def render_message_template(template: str, contact: Contact) -> str:
    context = {
        "id": str(contact.id),
        "name": contact.name,
        "phone": contact.phone,
        "tags": ", ".join(contact.tags or []),
    }

    def replacer(match: re.Match[str]) -> str:
        key = match.group(1)
        return context.get(key, match.group(0))

    return VARIABLE_PATTERN.sub(replacer, template)


async def bulk_send_messages(
    session: AsyncSession,
    message_template: str,
    contact_ids: list[int],
    workspace_id: int,
    template_id: int | None = None,
) -> BulkSendResponse:
    if not contact_ids:
        return BulkSendResponse(success_count=0, failed_count=0)

    template = None
    if template_id is not None:
        template = await get_template_by_id(
            session=session,
            workspace_id=workspace_id,
            template_id=template_id,
        )
        if not template:
            return BulkSendResponse(
                success_count=0,
                failed_count=len(contact_ids),
                results=[
                    BulkDeliveryResult(
                        contact_id=cid,
                        phone=None,
                        status="failed",
                        error="Template not found in workspace",
                    )
                    for cid in contact_ids
                ],
            )
        if template.status != TemplateStatus.approved:
            return BulkSendResponse(
                success_count=0,
                failed_count=len(contact_ids),
                results=[
                    BulkDeliveryResult(
                        contact_id=cid,
                        phone=None,
                        status="failed",
                        error="Template must be approved on Meta before sending",
                    )
                    for cid in contact_ids
                ],
            )
        if not template.meta_template_id:
            return BulkSendResponse(
                success_count=0,
                failed_count=len(contact_ids),
                results=[
                    BulkDeliveryResult(
                        contact_id=cid,
                        phone=None,
                        status="failed",
                        error="Template is not synced with Meta (missing meta_template_id)",
                    )
                    for cid in contact_ids
                ],
            )

    stmt = select(Contact).where(
        Contact.workspace_id == workspace_id,
        Contact.id.in_(contact_ids),
    )
    contacts = (await session.execute(stmt)).scalars().all()
    contacts_by_id = {contact.id: contact for contact in contacts}

    success_count = 0
    failed_count = 0
    results: list[BulkDeliveryResult] = []

    for contact_id in contact_ids:
        contact = contacts_by_id.get(contact_id)
        if not contact:
            failed_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact_id,
                    phone=None,
                    status="failed",
                    error="Contact not found in workspace",
                )
            )
            continue

        rendered_message = render_message_template(message_template, contact)

        try:
            await ensure_workspace_can_send(
                session=session,
                workspace_id=workspace_id,
                requested_count=1,
            )

            if template is not None:
                body_parameters = build_numbered_template_parameters(
                    text=template.body_text,
                    name=contact.name,
                    phone=contact.phone,
                )
                header_parameters = build_numbered_template_parameters(
                    text=template.header_content or "",
                    name=contact.name,
                    phone=contact.phone,
                )
                send_result = await send_whatsapp_template_message(
                    workspace_id=workspace_id,
                    phone=contact.phone,
                    template_name=template.name,
                    language=template.language,
                    body_parameters=body_parameters or None,
                    header_parameters=header_parameters or None,
                )
            else:
                send_result = await send_whatsapp_message(
                    workspace_id=workspace_id,
                    phone=contact.phone,
                    message=rendered_message,
                )
            provider_message_id = send_result.get("message_id")
            if isinstance(provider_message_id, str) and provider_message_id.strip():
                await register_sent_message(
                    session=session,
                    workspace_id=workspace_id,
                    provider_message_id=provider_message_id,
                    recipient_phone=contact.phone,
                )
            await record_message_event(
                session=session,
                workspace_id=workspace_id,
                campaign_id=None,
                contact_id=contact.id,
                status=MessageEventStatus.sent,
            )
            success_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact.id,
                    phone=contact.phone,
                    status="accepted",
                    provider=(
                        str(send_result.get("provider"))
                        if send_result.get("provider") is not None
                        else None
                    ),
                    message_id=(
                        provider_message_id
                        if isinstance(provider_message_id, str)
                        else None
                    ),
                    error=None,
                )
            )
        except BillingLimitExceeded as exc:
            logger.info(
                "Billing limit reached for workspace_id=%s: %s",
                workspace_id,
                str(exc),
            )
            failed_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact.id,
                    phone=contact.phone,
                    status="failed",
                    error=str(exc),
                )
            )
        except InvalidNumberError as exc:
            failed_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact.id,
                    phone=contact.phone,
                    status="failed",
                    error=str(exc),
                )
            )
        except RateLimitError as exc:
            failed_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact.id,
                    phone=contact.phone,
                    status="failed",
                    error=str(exc),
                )
            )
        except ApiError as exc:
            failed_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact.id,
                    phone=contact.phone,
                    status="failed",
                    error=str(exc),
                )
            )
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Failed to send message to contact_id=%s", contact_id)
            logger.debug("Bulk send exception details: %s", exc)
            failed_count += 1
            results.append(
                BulkDeliveryResult(
                    contact_id=contact.id,
                    phone=contact.phone,
                    status="failed",
                    error="Unexpected send error",
                )
            )

    if success_count > 0:
        await session.commit()

    return BulkSendResponse(
        success_count=success_count,
        failed_count=failed_count,
        results=results,
    )
