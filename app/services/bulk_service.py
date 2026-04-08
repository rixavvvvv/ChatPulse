import logging
import re

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.schemas.bulk import BulkSendResponse
from app.services.whatsapp_service import send_whatsapp_message

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
) -> BulkSendResponse:
    if not contact_ids:
        return BulkSendResponse(success_count=0, failed_count=0)

    stmt = select(Contact).where(
        Contact.workspace_id == workspace_id,
        Contact.id.in_(contact_ids),
    )
    contacts = (await session.execute(stmt)).scalars().all()
    contacts_by_id = {contact.id: contact for contact in contacts}

    success_count = 0
    failed_count = 0

    for contact_id in contact_ids:
        contact = contacts_by_id.get(contact_id)
        if not contact:
            failed_count += 1
            continue

        rendered_message = render_message_template(message_template, contact)

        try:
            await send_whatsapp_message(
                workspace_id=workspace_id,
                phone=contact.phone,
                message=rendered_message,
            )
            success_count += 1
        except Exception as exc:  # pragma: no cover
            logger.exception(
                "Failed to send message to contact_id=%s", contact_id)
            logger.debug("Bulk send exception details: %s", exc)
            failed_count += 1

    return BulkSendResponse(
        success_count=success_count,
        failed_count=failed_count,
    )
