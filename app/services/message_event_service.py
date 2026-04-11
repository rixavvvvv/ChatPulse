from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message_event import MessageEvent, MessageEventStatus
from app.services.usage_tracking_service import increment_messages_sent


async def record_message_event(
    session: AsyncSession,
    *,
    workspace_id: int,
    campaign_id: int | None,
    contact_id: int | None,
    status: MessageEventStatus,
    event_timestamp: datetime | None = None,
) -> MessageEvent:
    event = MessageEvent(
        workspace_id=workspace_id,
        campaign_id=campaign_id,
        contact_id=contact_id,
        status=status,
        timestamp=event_timestamp or datetime.now(tz=UTC),
    )
    session.add(event)

    if status == MessageEventStatus.sent:
        await increment_messages_sent(
            session=session,
            workspace_id=workspace_id,
            increment_by=1,
        )

    return event
