from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.message_event import MessageEvent, MessageEventStatus
from app.models.message_tracking import MessageTracking, MessageTrackingStatus
from app.schemas.analytics import (
    WorkspaceMessageAnalyticsResponse,
    WorkspaceMessageTimelinePoint,
    WorkspaceMessageTimelineResponse,
)


def _percentage(part: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((part / total) * 100, 2)


async def get_workspace_message_analytics(
    session: AsyncSession,
    workspace_id: int,
) -> WorkspaceMessageAnalyticsResponse:
    total_stmt = select(func.count(MessageTracking.id)).where(
        MessageTracking.workspace_id == workspace_id,
    )
    delivered_stmt = select(func.count(MessageTracking.id)).where(
        MessageTracking.workspace_id == workspace_id,
        MessageTracking.current_status.in_(
            [MessageTrackingStatus.delivered, MessageTrackingStatus.read]
        ),
    )
    read_stmt = select(func.count(MessageTracking.id)).where(
        MessageTracking.workspace_id == workspace_id,
        MessageTracking.current_status == MessageTrackingStatus.read,
    )
    failed_stmt = select(func.count(MessageTracking.id)).where(
        MessageTracking.workspace_id == workspace_id,
        MessageTracking.current_status == MessageTrackingStatus.failed,
    )

    total_sent = int((await session.execute(total_stmt)).scalar_one())
    delivered_count = int((await session.execute(delivered_stmt)).scalar_one())
    read_count = int((await session.execute(read_stmt)).scalar_one())
    failed_count = int((await session.execute(failed_stmt)).scalar_one())

    return WorkspaceMessageAnalyticsResponse(
        workspace_id=workspace_id,
        total_sent=total_sent,
        delivered_percentage=_percentage(delivered_count, total_sent),
        read_percentage=_percentage(read_count, total_sent),
        failure_percentage=_percentage(failed_count, total_sent),
    )


async def get_workspace_message_timeline(
    session: AsyncSession,
    workspace_id: int,
    days: int = 14,
) -> WorkspaceMessageTimelineResponse:
    window_days = min(max(days, 1), 90)
    start_date = (datetime.now(tz=UTC) - timedelta(days=window_days - 1)).date()

    stmt = (
        select(
            func.date(MessageEvent.timestamp).label("event_date"),
            MessageEvent.status,
            func.count(MessageEvent.id).label("count"),
        )
        .where(
            MessageEvent.workspace_id == workspace_id,
            MessageEvent.timestamp >= start_date,
            MessageEvent.status.in_(
                [
                    MessageEventStatus.sent,
                    MessageEventStatus.delivered,
                    MessageEventStatus.read,
                ]
            ),
        )
        .group_by(func.date(MessageEvent.timestamp), MessageEvent.status)
        .order_by(func.date(MessageEvent.timestamp).asc())
    )
    rows = (await session.execute(stmt)).all()

    points_by_date: dict[str, WorkspaceMessageTimelinePoint] = {}
    for index in range(window_days):
        current_date = (start_date + timedelta(days=index)).isoformat()
        points_by_date[current_date] = WorkspaceMessageTimelinePoint(
            date=current_date,
            sent=0,
            delivered=0,
        )

    for event_date, status, count in rows:
        date_key = event_date.isoformat()
        point = points_by_date.get(date_key)
        if point is None:
            continue

        numeric_count = int(count)
        if status == MessageEventStatus.sent:
            point.sent += numeric_count
        elif status in {MessageEventStatus.delivered, MessageEventStatus.read}:
            point.delivered += numeric_count

    return WorkspaceMessageTimelineResponse(
        workspace_id=workspace_id,
        points=[points_by_date[key] for key in sorted(points_by_date.keys())],
    )
