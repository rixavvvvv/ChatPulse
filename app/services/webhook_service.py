from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_contact import CampaignContact, CampaignContactDeliveryStatus, CampaignFailureClassification
from app.models.message_event import MessageEventStatus
from app.models.message_tracking import MessageTracking, MessageTrackingStatus
from app.services.message_event_service import record_message_event

_SUPPORTED_META_STATUS = {
    "delivered": MessageTrackingStatus.delivered,
    "read": MessageTrackingStatus.read,
    "failed": MessageTrackingStatus.failed,
}


@dataclass
class MetaWebhookProcessResult:
    processed: int = 0
    ignored: int = 0
    unknown_message: int = 0
    domain_events: list[tuple[str, int | None, dict[str, Any], str | None]] = field(
        default_factory=list
    )


async def _refresh_campaign_aggregates(
    session: AsyncSession,
    *,
    workspace_id: int,
    campaign_id: int,
) -> None:
    campaign_stmt = select(Campaign).where(
        Campaign.workspace_id == workspace_id,
        Campaign.id == campaign_id,
    )
    campaign = (await session.execute(campaign_stmt)).scalar_one_or_none()
    if not campaign:
        return

    total_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
    )
    sent_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.delivery_status == CampaignContactDeliveryStatus.sent,
    )
    failed_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.delivery_status == CampaignContactDeliveryStatus.failed,
    )
    skipped_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.delivery_status == CampaignContactDeliveryStatus.skipped,
    )

    total_count = int((await session.execute(total_stmt)).scalar_one())
    campaign.success_count = int((await session.execute(sent_stmt)).scalar_one())
    campaign.failed_count = int((await session.execute(failed_stmt)).scalar_one())
    skipped_count = int((await session.execute(skipped_stmt)).scalar_one())
    processed_count = campaign.success_count + campaign.failed_count + skipped_count

    if campaign.failed_count > 0:
        first_failure_stmt = select(CampaignContact.last_error).where(
            CampaignContact.workspace_id == workspace_id,
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.delivery_status == CampaignContactDeliveryStatus.failed,
        ).order_by(CampaignContact.id.asc()).limit(1)
        first_failure = (await session.execute(first_failure_stmt)).scalar_one_or_none()
        campaign.last_error = first_failure
    else:
        campaign.last_error = None

    if total_count > 0 and processed_count >= total_count:
        campaign.status = CampaignStatus.failed if campaign.failed_count >= total_count else CampaignStatus.completed


def _parse_meta_timestamp(raw_timestamp: Any) -> datetime | None:
    if raw_timestamp is None:
        return None

    if isinstance(raw_timestamp, (int, float)):
        return datetime.fromtimestamp(float(raw_timestamp), tz=UTC)

    if isinstance(raw_timestamp, str):
        try:
            return datetime.fromtimestamp(float(raw_timestamp), tz=UTC)
        except ValueError:
            return None

    return None


def _extract_error_message(status_payload: dict[str, Any]) -> str | None:
    errors = status_payload.get("errors")
    if not isinstance(errors, list) or not errors:
        return None

    first = errors[0]
    if not isinstance(first, dict):
        return None

    details = first.get("details")
    if isinstance(details, str) and details.strip():
        return details

    message = first.get("message")
    if isinstance(message, str) and message.strip():
        return message

    title = first.get("title")
    if isinstance(title, str) and title.strip():
        return title

    return None


async def register_sent_message(
    session: AsyncSession,
    *,
    workspace_id: int,
    provider_message_id: str,
    recipient_phone: str | None,
    campaign_id: int | None = None,
    campaign_contact_id: int | None = None,
) -> MessageTracking:
    stmt = select(MessageTracking).where(
        MessageTracking.provider_message_id == provider_message_id,
    )
    tracking = (await session.execute(stmt)).scalar_one_or_none()

    now = datetime.now(tz=UTC)
    if tracking:
        tracking.workspace_id = workspace_id
        tracking.recipient_phone = recipient_phone
        tracking.campaign_id = campaign_id
        tracking.campaign_contact_id = campaign_contact_id
        if tracking.sent_at is None:
            tracking.sent_at = now
        if tracking.current_status == MessageTrackingStatus.failed:
            tracking.current_status = MessageTrackingStatus.sent
            tracking.last_error = None
        return tracking

    tracking = MessageTracking(
        workspace_id=workspace_id,
        provider_message_id=provider_message_id,
        recipient_phone=recipient_phone,
        campaign_id=campaign_id,
        campaign_contact_id=campaign_contact_id,
        current_status=MessageTrackingStatus.sent,
        sent_at=now,
    )
    session.add(tracking)
    return tracking


async def process_meta_webhook_payload(
    session: AsyncSession,
    payload: dict[str, Any],
) -> MetaWebhookProcessResult:
    result = MetaWebhookProcessResult()
    impacted_campaigns: set[tuple[int, int]] = set()

    entries = payload.get("entry")
    if not isinstance(entries, list):
        return result

    for entry in entries:
        if not isinstance(entry, dict):
            continue

        changes = entry.get("changes")
        if not isinstance(changes, list):
            continue

        for change in changes:
            if not isinstance(change, dict):
                continue

            value = change.get("value")
            if not isinstance(value, dict):
                continue

            statuses = value.get("statuses")
            if not isinstance(statuses, list):
                continue

            for status_payload in statuses:
                if not isinstance(status_payload, dict):
                    result.ignored += 1
                    continue

                raw_status = status_payload.get("status")
                if not isinstance(raw_status, str):
                    result.ignored += 1
                    continue

                normalized_status = raw_status.strip().lower()
                target_status = _SUPPORTED_META_STATUS.get(normalized_status)
                if target_status is None:
                    result.ignored += 1
                    continue

                provider_message_id = status_payload.get("id")
                if not isinstance(provider_message_id, str) or not provider_message_id.strip():
                    result.ignored += 1
                    continue
                provider_message_id = provider_message_id.strip()

                stmt = select(MessageTracking).where(
                    MessageTracking.provider_message_id == provider_message_id,
                )
                tracking = (await session.execute(stmt)).scalar_one_or_none()
                if not tracking:
                    result.unknown_message += 1
                    continue

                webhook_time = _parse_meta_timestamp(
                    status_payload.get("timestamp"))
                if tracking.last_webhook_at and webhook_time and webhook_time < tracking.last_webhook_at:
                    result.ignored += 1
                    continue

                tracking.current_status = target_status
                tracking.last_webhook_at = webhook_time or datetime.now(tz=UTC)
                tracking.last_webhook_payload = status_payload

                if target_status == MessageTrackingStatus.delivered and tracking.delivered_at is None:
                    tracking.delivered_at = tracking.last_webhook_at
                elif target_status == MessageTrackingStatus.read and tracking.read_at is None:
                    tracking.read_at = tracking.last_webhook_at
                elif target_status == MessageTrackingStatus.failed:
                    tracking.failed_at = tracking.last_webhook_at
                    tracking.last_error = _extract_error_message(
                        status_payload)

                event_status = MessageEventStatus(target_status.value)
                contact_id: int | None = None
                if tracking.campaign_contact_id is not None:
                    contact_stmt = select(CampaignContact).where(
                        CampaignContact.id == tracking.campaign_contact_id,
                        CampaignContact.workspace_id == tracking.workspace_id,
                    )
                    campaign_contact = (await session.execute(contact_stmt)).scalar_one_or_none()
                    if campaign_contact:
                        contact_id = campaign_contact.source_contact_id
                    if campaign_contact and target_status == MessageTrackingStatus.failed:
                        campaign_contact.delivery_status = CampaignContactDeliveryStatus.failed
                        campaign_contact.failure_classification = CampaignFailureClassification.api_error
                        campaign_contact.last_error = tracking.last_error

                if tracking.campaign_id is not None:
                    impacted_campaigns.add(
                        (tracking.workspace_id, tracking.campaign_id))

                await record_message_event(
                    session=session,
                    workspace_id=tracking.workspace_id,
                    campaign_id=tracking.campaign_id,
                    contact_id=contact_id,
                    status=event_status,
                    event_timestamp=tracking.last_webhook_at,
                )

                result.domain_events.append(
                    (
                        "whatsapp.message_status",
                        tracking.workspace_id,
                        {
                            "provider_message_id": provider_message_id,
                            "status": normalized_status,
                            "recipient_id": status_payload.get("recipient_id"),
                            "errors": status_payload.get("errors"),
                        },
                        f"wamid:{provider_message_id}:{normalized_status}",
                    )
                )

                result.processed += 1

            messages = value.get("messages")
            if isinstance(messages, list):
                contacts_payload = value.get("contacts", [])
                contacts_dict = {
                    str(c.get("wa_id")): c.get("profile", {}).get("name", "Unknown Contact")
                    for c in contacts_payload if isinstance(c, dict)
                }

                # Find workspace_id from phone_number_id
                metadata = value.get("metadata", {})
                phone_number_id = metadata.get("phone_number_id")
                if not phone_number_id:
                    result.ignored += len(messages)
                    continue

                from app.models.meta_credential import MetaCredential
                stmt = select(MetaCredential).where(MetaCredential.phone_number_id == str(phone_number_id))
                cred = (await session.execute(stmt)).scalar_one_or_none()
                if not cred:
                    result.ignored += len(messages)
                    continue
                workspace_id = cred.workspace_id

                from app.models.contact import Contact
                from app.services.contact_service import create_contact
                from app.services.conversation_message_service import create_inbound_message
                from app.models.conversation import MessageContentType

                for msg_payload in messages:
                    if not isinstance(msg_payload, dict):
                        result.ignored += 1
                        continue
                    
                    from_phone = str(msg_payload.get("from"))
                    msg_id = str(msg_payload.get("id"))
                    contact_name = contacts_dict.get(from_phone, "Unknown Contact")
                    
                    # Ensure contact exists
                    contact_stmt = select(Contact).where(
                        Contact.workspace_id == workspace_id,
                        Contact.phone == from_phone,
                    ).order_by(Contact.id.asc()).limit(1)
                    contact = (await session.execute(contact_stmt)).scalar_one_or_none()
                    
                    if not contact:
                        contact = await create_contact(session, workspace_id, contact_name, from_phone)

                    # Parse message content
                    msg_type = msg_payload.get("type", "text")
                    content = ""
                    content_type = MessageContentType.text

                    if msg_type == "text":
                        content = msg_payload.get("text", {}).get("body", "")
                    elif msg_type == "image":
                        content = "[Image]"
                        content_type = MessageContentType.image
                    elif msg_type == "document":
                        content = "[Document]"
                        content_type = MessageContentType.document
                    elif msg_type == "video":
                        content = "[Video]"
                        content_type = MessageContentType.video
                    elif msg_type == "audio":
                        content = "[Audio]"
                        content_type = MessageContentType.audio
                    elif msg_type == "location":
                        content = "[Location]"
                        content_type = MessageContentType.location
                    elif msg_type == "interactive":
                        # Button reply or list reply
                        interactive = msg_payload.get("interactive", {})
                        if interactive.get("type") == "button_reply":
                            content = interactive.get("button_reply", {}).get("title", "[Button]")
                        elif interactive.get("type") == "list_reply":
                            content = interactive.get("list_reply", {}).get("title", "[List]")
                        else:
                            content = "[Interactive]"
                        content_type = MessageContentType.interactive
                    else:
                        content = f"[{msg_type.capitalize()}]"

                    # Create inbound message and conversation
                    message, conversation = await create_inbound_message(
                        db=session,
                        workspace_id=workspace_id,
                        contact_id=contact.id,
                        content=content,
                        content_type=content_type,
                        provider_message_id=msg_id,
                        metadata_json=msg_payload,
                    )
                    
                    result.domain_events.append(
                        (
                            "whatsapp.message_received",
                            workspace_id,
                            {"contact_id": contact.id, "provider_message_id": msg_id, "type": msg_type},
                            f"inbound:{msg_id}",
                        )
                    )
                    
                    # Notify via WebSockets
                    from app.services.websocket_manager import get_distributed_manager
                    from app.services.redis_pubsub_manager import get_conversation_channel, get_workspace_channel
                    manager = get_distributed_manager()
                    
                    event = {
                        "event_type": "message.created",
                        "conversation_id": conversation.id,
                        "message": {
                            "id": message.id,
                            "content": message.content,
                            "direction": message.direction.value,
                            "created_at": message.created_at.isoformat() if message.created_at else None,
                        }
                    }
                    await manager.broadcast_to_room(get_conversation_channel(conversation.id), event)
                    await manager.broadcast_to_room(get_workspace_channel(workspace_id), event)
                    
                    result.processed += 1

    for workspace_id, campaign_id in impacted_campaigns:
        await _refresh_campaign_aggregates(
            session=session,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
        )

    await session.commit()
    return result
