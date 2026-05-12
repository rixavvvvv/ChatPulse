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

# ─────────────────────────────────────────────────────────────────────────────
# Legacy Analytics Functions (kept for backwards compatibility)
# ─────────────────────────────────────────────────────────────────────────────


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


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Event Storage Infrastructure
# ─────────────────────────────────────────────────────────────────────────────

"""
Analytics event storage service for ChatPulse.

Provides:
- Event ingestion pipeline
- Event querying and filtering
- Aggregation helpers
- Real-time metrics
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any, AsyncGenerator

from sqlalchemy import and_, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession as AsyncSessionAlt
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.db import get_db_session
from app.models.analytics import (
    AnalyticsEvent,
    AnalyticsRollup,
    CampaignMetrics,
    EventCategory,
    EventType,
    RealtimeMetrics,
    RollupGranularity,
    WorkspaceMetrics,
    create_event_id,
    get_aggregation_key,
)
from app.services.queue_service import get_queue_service

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Event Ingestion Service
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsIngestionService:
    """
    Service for ingesting analytics events.

    Events are written to the append-only event log.
    Background workers process events for aggregation.
    """

    def __init__(self, redis_client=None):
        self._redis = redis_client

    async def ingest_event(
        self,
        event_type: str | EventType,
        workspace_id: int,
        event_data: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
        campaign_id: int | None = None,
        user_id: int | None = None,
        contact_id: int | None = None,
        queue_name: str | None = None,
        task_id: str | None = None,
        worker_id: str | None = None,
        value_numeric: float | None = None,
        duration_ms: float | None = None,
        count: int | None = None,
        source: str | None = None,
        trace_id: str | None = None,
        request_id: str | None = None,
        success: bool | None = None,
        error_type: str | None = None,
        labels: dict[str, str] | None = None,
    ) -> AnalyticsEvent:
        """
        Ingest a single analytics event.

        Args:
            event_type: Type of event (e.g., "message.sent")
            workspace_id: Workspace ID
            event_data: Additional event data
            occurred_at: When event occurred (defaults to now)
            campaign_id: Optional campaign ID
            user_id: Optional user ID
            contact_id: Optional contact ID
            queue_name: Optional queue name
            task_id: Optional task ID
            worker_id: Optional worker ID
            value_numeric: Numeric value for aggregation
            duration_ms: Duration in milliseconds
            count: Count for aggregation
            source: Event source
            trace_id: Trace ID for correlation
            request_id: Request ID
            success: Whether event was successful
            error_type: Error type if failed
            labels: Dimension labels

        Returns:
            Created AnalyticsEvent
        """
        event_type_str = event_type.value if isinstance(event_type, EventType) else event_type
        category = self._get_category(event_type_str)

        event = AnalyticsEvent(
            event_id=create_event_id(),
            event_type=event_type_str,
            event_category=category,
            occurred_at=occurred_at or datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            user_id=user_id,
            contact_id=contact_id,
            queue_name=queue_name,
            task_id=task_id,
            worker_id=worker_id,
            event_data=event_data or {},
            value_numeric=value_numeric,
            duration_ms=duration_ms,
            count=count,
            source=source,
            trace_id=trace_id,
            request_id=request_id,
            success=success,
            error_type=error_type,
            labels=labels,
            processed=False,
            aggregation_key=get_aggregation_key(event_type_str, workspace_id, labels, category),
        )

        async with get_db_session() as session:
            session.add(event)
            await session.commit()
            await session.refresh(event)

        # Publish to Redis for real-time consumers
        if self._redis:
            await self._publish_realtime_event(event)

        return event

    async def ingest_batch(
        self,
        events: list[dict[str, Any]],
    ) -> list[AnalyticsEvent]:
        """
        Ingest multiple events in a batch.

        Args:
            events: List of event dictionaries

        Returns:
            List of created AnalyticsEvents
        """
        created_events = []

        async with get_db_session() as session:
            for event_dict in events:
                event_type = event_dict.get("event_type")
                category = self._get_category(event_type)

                event = AnalyticsEvent(
                    event_id=create_event_id(),
                    event_type=event_type,
                    event_category=category,
                    occurred_at=event_dict.get("occurred_at") or datetime.now(timezone.utc),
                    ingested_at=datetime.now(timezone.utc),
                    workspace_id=event_dict["workspace_id"],
                    campaign_id=event_dict.get("campaign_id"),
                    user_id=event_dict.get("user_id"),
                    contact_id=event_dict.get("contact_id"),
                    queue_name=event_dict.get("queue_name"),
                    task_id=event_dict.get("task_id"),
                    worker_id=event_dict.get("worker_id"),
                    event_data=event_dict.get("event_data", {}),
                    value_numeric=event_dict.get("value_numeric"),
                    duration_ms=event_dict.get("duration_ms"),
                    count=event_dict.get("count"),
                    source=event_dict.get("source"),
                    trace_id=event_dict.get("trace_id"),
                    request_id=event_dict.get("request_id"),
                    success=event_dict.get("success"),
                    error_type=event_dict.get("error_type"),
                    labels=event_dict.get("labels"),
                    processed=False,
                    aggregation_key=get_aggregation_key(event_type, event_dict["workspace_id"], event_dict.get("labels"), category),
                )
                session.add(event)
                created_events.append(event)

            await session.commit()

        return created_events

    async def _publish_realtime_event(self, event: AnalyticsEvent) -> None:
        """Publish event to Redis for real-time consumers."""
        try:
            import redis.asyncio as redis
            channel = f"analytics:events:{event.event_category}"
            message = json.dumps({
                "event_id": str(event.event_id),
                "event_type": event.event_type,
                "workspace_id": event.workspace_id,
                "occurred_at": event.occurred_at.isoformat(),
            })
            await self._redis.publish(channel, message)
        except Exception as exc:
            logger.warning(f"Failed to publish realtime event: {exc}")

    def _get_category(self, event_type: str) -> str:
        """Get event category from event type."""
        category_map = {
            "message.": EventCategory.MESSAGE.value,
            "webhook.": EventCategory.WEBHOOK.value,
            "campaign.": EventCategory.CAMPAIGN.value,
            "recovery.": EventCategory.RECOVERY.value,
            "rate_limit.": EventCategory.RATE_LIMIT.value,
            "api.": EventCategory.API.value,
            "queue.": EventCategory.QUEUE.value,
            "segment.": EventCategory.SEGMENT.value,
            "contact.": EventCategory.CONTACT.value,
            "user.": EventCategory.USER.value,
        }

        for prefix, category in category_map.items():
            if event_type.startswith(prefix):
                return category

        return "unknown"


# ─────────────────────────────────────────────────────────────────────────────
# Event Query Service
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsQueryService:
    """Service for querying analytics data."""

    async def get_events(
        self,
        workspace_id: int,
        event_types: list[str] | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        limit: int = 100,
        offset: int = 0,
    ) -> list[AnalyticsEvent]:
        """Query events for a workspace."""
        async with get_db_session() as session:
            query = select(AnalyticsEvent).where(
                AnalyticsEvent.workspace_id == workspace_id
            )

            if event_types:
                query = query.where(AnalyticsEvent.event_type.in_(event_types))

            if start_time:
                query = query.where(AnalyticsEvent.occurred_at >= start_time)

            if end_time:
                query = query.where(AnalyticsEvent.occurred_at <= end_time)

            query = query.order_by(AnalyticsEvent.occurred_at.desc())
            query = query.limit(limit).offset(offset)

            result = await session.execute(query)
            return result.scalars().all()

    async def get_event_counts(
        self,
        workspace_id: int,
        event_type: str,
        start_time: datetime,
        end_time: datetime,
    ) -> int:
        """Get count of events in time range."""
        async with get_db_session() as session:
            query = select(func.count()).where(
                and_(
                    AnalyticsEvent.workspace_id == workspace_id,
                    AnalyticsEvent.event_type == event_type,
                    AnalyticsEvent.occurred_at >= start_time,
                    AnalyticsEvent.occurred_at <= end_time,
                )
            )
            result = await session.execute(query)
            return result.scalar() or 0

    async def get_rollups(
        self,
        workspace_id: int,
        rollup_key: str,
        granularity: RollupGranularity,
        start_time: datetime,
        end_time: datetime,
    ) -> list[AnalyticsRollup]:
        """Query pre-computed rollups."""
        async with get_db_session() as session:
            query = select(AnalyticsRollup).where(
                and_(
                    AnalyticsRollup.workspace_id == workspace_id,
                    AnalyticsRollup.rollup_key == rollup_key,
                    AnalyticsRollup.granularity == granularity.value,
                    AnalyticsRollup.window_start >= start_time,
                    AnalyticsRollup.window_end <= end_time,
                )
            ).order_by(AnalyticsRollup.window_start)

            result = await session.execute(query)
            return result.scalars().all()

    async def get_workspace_metrics(
        self,
        workspace_id: int,
        period_start: datetime,
        period_end: datetime,
    ) -> WorkspaceMetrics | None:
        """Get workspace metrics for a period."""
        async with get_db_session() as session:
            query = select(WorkspaceMetrics).where(
                and_(
                    WorkspaceMetrics.workspace_id == workspace_id,
                    WorkspaceMetrics.period_start == period_start,
                    WorkspaceMetrics.period_end == period_end,
                )
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_campaign_metrics(
        self,
        campaign_id: int,
    ) -> CampaignMetrics | None:
        """Get campaign metrics."""
        async with get_db_session() as session:
            query = select(CampaignMetrics).where(
                CampaignMetrics.campaign_id == campaign_id
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()

    async def get_realtime_metrics(
        self,
        workspace_id: int,
    ) -> RealtimeMetrics | None:
        """Get real-time metrics for a workspace."""
        async with get_db_session() as session:
            query = select(RealtimeMetrics).where(
                RealtimeMetrics.workspace_id == workspace_id
            )
            result = await session.execute(query)
            return result.scalar_one_or_none()


# ─────────────────────────────────────────────────────────────────────────────
# Real-time Metrics Service
# ─────────────────────────────────────────────────────────────────────────────

class RealtimeMetricsService:
    """Service for real-time metrics updates."""

    def __init__(self, redis_client=None):
        self._redis = redis_client

    async def update_realtime(
        self,
        workspace_id: int,
        campaign_id: int | None = None,
        **kwargs,
    ) -> None:
        """Update real-time metrics."""
        async with get_db_session() as session:
            # Upsert realtime metrics
            query = select(RealtimeMetrics).where(
                RealtimeMetrics.workspace_id == workspace_id
            )
            result = await session.execute(query)
            metrics = result.scalar_one_or_none()

            if metrics is None:
                metrics = RealtimeMetrics(workspace_id=workspace_id)
                session.add(metrics)

            # Update fields
            for key, value in kwargs.items():
                if hasattr(metrics, key):
                    setattr(metrics, key, value)

            metrics.updated_at = datetime.now(timezone.utc)
            await session.commit()

    async def increment_counter(
        self,
        workspace_id: int,
        counter_name: str,
        amount: int = 1,
    ) -> None:
        """Increment a real-time counter."""
        async with get_db_session() as session:
            query = select(RealtimeMetrics).where(
                RealtimeMetrics.workspace_id == workspace_id
            )
            result = await session.execute(query)
            metrics = result.scalar_one_or_none()

            if metrics is None:
                metrics = RealtimeMetrics(workspace_id=workspace_id)
                session.add(metrics)

            # Map counter names to fields
            counter_map = {
                "messages_sent": "messages_last_minute",
                "messages_last_hour": "messages_last_hour",
                "webhooks_received": "webhooks_last_minute",
                "webhooks_last_hour": "webhooks_last_hour",
            }

            if counter_name in counter_map:
                field = counter_map[counter_name]
                current = getattr(metrics, field, 0) or 0
                setattr(metrics, field, current + amount)

            metrics.updated_at = datetime.now(timezone.utc)
            await session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Event Factory
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsEventFactory:
    """Factory for creating analytics events from service calls."""

    @staticmethod
    async def from_message_event(
        workspace_id: int,
        campaign_id: int,
        event_type: str,
        contact_id: int | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        error_type: str | None = None,
        trace_id: str | None = None,
    ) -> AnalyticsEvent:
        """Create event from message dispatch."""
        ingestion = AnalyticsIngestionService()
        return await ingestion.ingest_event(
            event_type=event_type,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            contact_id=contact_id,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            trace_id=trace_id,
        )

    @staticmethod
    async def from_webhook_event(
        workspace_id: int,
        source: str,
        event_type: str,
        duration_ms: float | None = None,
        success: bool = True,
        error_type: str | None = None,
        trace_id: str | None = None,
    ) -> AnalyticsEvent:
        """Create event from webhook processing."""
        ingestion = AnalyticsIngestionService()
        return await ingestion.ingest_event(
            event_type=event_type,
            workspace_id=workspace_id,
            source=source,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            trace_id=trace_id,
        )

    @staticmethod
    async def from_campaign_event(
        workspace_id: int,
        campaign_id: int,
        event_type: str,
        recipient_count: int | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        error_type: str | None = None,
        trace_id: str | None = None,
    ) -> AnalyticsEvent:
        """Create event from campaign lifecycle."""
        ingestion = AnalyticsIngestionService()
        return await ingestion.ingest_event(
            event_type=event_type,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            count=recipient_count,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            trace_id=trace_id,
        )

    @staticmethod
    async def from_recovery_event(
        workspace_id: int,
        campaign_id: int,
        event_type: str,
        duration_ms: float | None = None,
        recipients_resumed: int | None = None,
        success: bool = True,
        error_type: str | None = None,
        trace_id: str | None = None,
    ) -> AnalyticsEvent:
        """Create event from recovery operation."""
        ingestion = AnalyticsIngestionService()
        return await ingestion.ingest_event(
            event_type=event_type,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            count=recipients_resumed,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            trace_id=trace_id,
        )

    @staticmethod
    async def from_queue_task(
        workspace_id: int,
        queue_name: str,
        task_id: str,
        task_name: str,
        event_type: str,
        worker_id: str | None = None,
        duration_ms: float | None = None,
        success: bool = True,
        error_type: str | None = None,
        trace_id: str | None = None,
    ) -> AnalyticsEvent:
        """Create event from queue task lifecycle."""
        ingestion = AnalyticsIngestionService()
        return await ingestion.ingest_event(
            event_type=event_type,
            workspace_id=workspace_id,
            queue_name=queue_name,
            task_id=task_id,
            worker_id=worker_id,
            duration_ms=duration_ms,
            success=success,
            error_type=error_type,
            trace_id=trace_id,
            labels={"task_name": task_name} if task_name else None,
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
