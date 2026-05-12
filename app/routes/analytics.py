from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.analytics import (
    WorkspaceMessageAnalyticsResponse,
    WorkspaceMessageTimelineResponse,
)
from app.services.analytics_service import (
    get_workspace_message_analytics,
    get_workspace_message_timeline,
)

# ─────────────────────────────────────────────────────────────────────────────
# Legacy Analytics Routes (kept for backwards compatibility)
# ─────────────────────────────────────────────────────────────────────────────

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/messages", response_model=WorkspaceMessageAnalyticsResponse)
async def workspace_message_analytics_route(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> WorkspaceMessageAnalyticsResponse:
    return await get_workspace_message_analytics(
        session=session,
        workspace_id=workspace.id,
    )


@router.get("/messages/timeline", response_model=WorkspaceMessageTimelineResponse)
async def workspace_message_timeline_route(
    days: int = 14,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> WorkspaceMessageTimelineResponse:
    return await get_workspace_message_timeline(
        session=session,
        workspace_id=workspace.id,
        days=days,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Event Storage API Routes
# ─────────────────────────────────────────────────────────────────────────────

"""
Analytics API routes for event storage infrastructure.

Provides:
- Event listing and filtering
- Metrics querying
- Rollup data
- Real-time metrics
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.dependencies.auth import get_current_user
from app.models.analytics import (
    EventType,
    RollupGranularity,
)
from app.services.analytics_service import (
    AnalyticsIngestionService,
    AnalyticsQueryService,
    RealtimeMetricsService,
)

logger = logging.getLogger(__name__)
events_router = APIRouter(prefix="/analytics", tags=["Analytics Events"])


# ─────────────────────────────────────────────────────────────────────────────
# Request/Response Models
# ─────────────────────────────────────────────────────────────────────────────

class EventQuery(BaseModel):
    """Query parameters for event filtering."""

    event_types: list[str] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    limit: int = Field(default=100, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)


class EventResponse(BaseModel):
    """Event response model."""

    id: int
    event_id: str
    event_type: str
    event_category: str
    occurred_at: datetime
    workspace_id: int
    campaign_id: int | None = None
    success: bool | None = None
    error_type: str | None = None
    duration_ms: float | None = None
    labels: dict | None = None

    class Config:
        from_attributes = True


class EventsListResponse(BaseModel):
    """List of events response."""

    events: list[EventResponse]
    total: int
    limit: int
    offset: int


class RollupResponse(BaseModel):
    """Rollup response model."""

    id: int
    workspace_id: int
    rollup_key: str
    granularity: str
    window_start: datetime
    window_end: datetime
    event_type: str
    total_count: int
    success_count: int
    failure_count: int
    value_avg: float | None = None
    duration_avg: float | None = None
    duration_p50: float | None = None
    duration_p95: float | None = None
    duration_p99: float | None = None

    class Config:
        from_attributes = True


class WorkspaceMetricsResponse(BaseModel):
    """Workspace metrics response."""

    workspace_id: int
    period_start: datetime
    period_end: datetime
    messages_sent: int
    messages_delivered: int
    messages_failed: int
    delivery_rate: float | None = None
    campaigns_created: int
    campaigns_completed: int
    campaigns_failed: int
    webhooks_received: int
    webhooks_processed: int
    webhooks_failed: int
    recoveries_detected: int
    recoveries_completed: int
    recoveries_failed: int
    rate_limit_allowed: int
    rate_limit_rejected: int

    class Config:
        from_attributes = True


class CampaignMetricsResponse(BaseModel):
    """Campaign metrics response."""

    campaign_id: int
    workspace_id: int
    total_recipients: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    delivery_rate: float | None = None
    read_rate: float | None = None
    failure_rate: float | None = None
    avg_per_recipient_ms: float | None = None
    recovery_count: int
    final_status: str | None = None

    class Config:
        from_attributes = True


class RealtimeMetricsResponse(BaseModel):
    """Real-time metrics response."""

    workspace_id: int
    active_campaigns: int
    messages_in_flight: int
    queue_depth: int
    active_workers: int
    messages_last_minute: int
    messages_last_hour: int
    messages_per_second: float | None = None
    avg_queue_latency_ms: float | None = None
    avg_dispatch_latency_ms: float | None = None
    p95_dispatch_latency_ms: float | None = None
    error_rate_percent: float | None = None
    updated_at: datetime

    class Config:
        from_attributes = True


class DashboardSummaryResponse(BaseModel):
    """Dashboard summary response."""

    workspace_id: int
    period: str
    messages_sent_today: int
    messages_sent_yesterday: int
    campaigns_active: int
    campaigns_completed_today: int
    delivery_rate: float
    avg_dispatch_time_ms: float
    queue_depth: int
    error_rate: float


# ─────────────────────────────────────────────────────────────────────────────
# Event Routes
# ─────────────────────────────────────────────────────────────────────────────

@events_router.get("/events", response_model=EventsListResponse)
async def list_events(
    workspace_id: int,
    event_types: list[str] | None = Query(None),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    user=Depends(get_current_user),
) -> EventsListResponse:
    """
    List analytics events for a workspace.

    Args:
        workspace_id: Workspace ID
        event_types: Filter by event types
        start_time: Start time filter
        end_time: End time filter
        limit: Number of results
        offset: Pagination offset

    Returns:
        List of events with pagination
    """
    query_service = AnalyticsQueryService()

    events = await query_service.get_events(
        workspace_id=workspace_id,
        event_types=event_types,
        start_time=start_time,
        end_time=end_time,
        limit=limit,
        offset=offset,
    )

    return EventsListResponse(
        events=[
            EventResponse(
                id=e.id,
                event_id=str(e.event_id),
                event_type=e.event_type,
                event_category=e.event_category,
                occurred_at=e.occurred_at,
                workspace_id=e.workspace_id,
                campaign_id=e.campaign_id,
                success=e.success,
                error_type=e.error_type,
                duration_ms=e.duration_ms,
                labels=e.labels,
            )
            for e in events
        ],
        total=len(events),
        limit=limit,
        offset=offset,
    )


@events_router.get("/events/count")
async def get_event_count(
    workspace_id: int,
    event_type: str,
    start_time: datetime,
    end_time: datetime,
    user=Depends(get_current_user),
) -> dict[str, Any]:
    """
    Get count of events in time range.

    Args:
        workspace_id: Workspace ID
        event_type: Event type to count
        start_time: Start time
        end_time: End time

    Returns:
        Event count
    """
    query_service = AnalyticsQueryService()
    count = await query_service.get_event_counts(
        workspace_id=workspace_id,
        event_type=event_type,
        start_time=start_time,
        end_time=end_time,
    )

    return {"count": count, "event_type": event_type}


# ─────────────────────────────────────────────────────────────────────────────
# Rollup Routes
# ─────────────────────────────────────────────────────────────────────────────

@events_router.get("/rollups", response_model=list[RollupResponse])
async def list_rollups(
    workspace_id: int,
    rollup_key: str,
    granularity: str = Query(default="1h"),
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    user=Depends(get_current_user),
) -> list[RollupResponse]:
    """
    List rollups for a workspace.

    Args:
        workspace_id: Workspace ID
        rollup_key: Rollup key to filter
        granularity: Time granularity
        start_time: Start time filter
        end_time: End time filter

    Returns:
        List of rollups
    """
    query_service = AnalyticsQueryService()

    if end_time is None:
        end_time = datetime.now(timezone.utc)
    if start_time is None:
        start_time = end_time - timedelta(days=7)

    rollups = await query_service.get_rollups(
        workspace_id=workspace_id,
        rollup_key=rollup_key,
        granularity=RollupGranularity(granularity),
        start_time=start_time,
        end_time=end_time,
    )

    return [
        RollupResponse(
            id=r.id,
            workspace_id=r.workspace_id,
            rollup_key=r.rollup_key,
            granularity=r.granularity,
            window_start=r.window_start,
            window_end=r.window_end,
            event_type=r.event_type,
            total_count=r.total_count,
            success_count=r.success_count,
            failure_count=r.failure_count,
            value_avg=r.value_avg,
            duration_avg=r.duration_avg,
            duration_p50=r.duration_p50,
            duration_p95=r.duration_p95,
            duration_p99=r.duration_p99,
        )
        for r in rollups
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Metrics Routes
# ─────────────────────────────────────────────────────────────────────────────

@events_router.get("/workspace", response_model=WorkspaceMetricsResponse)
async def get_workspace_metrics(
    workspace_id: int,
    period_start: datetime | None = None,
    period_end: datetime | None = None,
    user=Depends(get_current_user),
) -> WorkspaceMetricsResponse:
    """
    Get workspace metrics for a period.

    Args:
        workspace_id: Workspace ID
        period_start: Period start (defaults to yesterday)
        period_end: Period end (defaults to today)

    Returns:
        Workspace metrics
    """
    query_service = AnalyticsQueryService()

    if period_end is None:
        period_end = datetime.now(timezone.utc)
    if period_start is None:
        period_start = period_end.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)

    metrics = await query_service.get_workspace_metrics(
        workspace_id=workspace_id,
        period_start=period_start,
        period_end=period_end,
    )

    if metrics is None:
        raise HTTPException(status_code=404, detail="Metrics not found")

    return WorkspaceMetricsResponse(
        workspace_id=metrics.workspace_id,
        period_start=metrics.period_start,
        period_end=metrics.period_end,
        messages_sent=metrics.messages_sent,
        messages_delivered=metrics.messages_delivered,
        messages_failed=metrics.messages_failed,
        delivery_rate=metrics.message_delivery_rate,
        campaigns_created=metrics.campaigns_created,
        campaigns_completed=metrics.campaigns_completed,
        campaigns_failed=metrics.campaigns_failed,
        webhooks_received=metrics.webhooks_received,
        webhooks_processed=metrics.webhooks_processed,
        webhooks_failed=metrics.webhooks_failed,
        recoveries_detected=metrics.recoveries_detected,
        recoveries_completed=metrics.recoveries_completed,
        recoveries_failed=metrics.recoveries_failed,
        rate_limit_allowed=metrics.rate_limit_allowed,
        rate_limit_rejected=metrics.rate_limit_rejected,
    )


@events_router.get("/workspace/dashboard")
async def get_dashboard_summary(
    workspace_id: int,
    period: str = Query(default="today"),
    user=Depends(get_current_user),
) -> DashboardSummaryResponse:
    """
    Get dashboard summary for a workspace.

    Args:
        workspace_id: Workspace ID
        period: Time period (today, yesterday, last7days)

    Returns:
        Dashboard summary
    """
    query_service = AnalyticsQueryService()

    now = datetime.now(timezone.utc)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday_start = today_start - timedelta(days=1)

    if period == "today":
        start_time = today_start
        end_time = now
    elif period == "yesterday":
        start_time = yesterday_start
        end_time = today_start
    else:  # last7days
        start_time = today_start - timedelta(days=7)
        end_time = now

    # Get today's metrics
    today_metrics = await query_service.get_workspace_metrics(
        workspace_id=workspace_id,
        period_start=today_start,
        period_end=now,
    )

    # Get yesterday's metrics
    yesterday_metrics = await query_service.get_workspace_metrics(
        workspace_id=workspace_id,
        period_start=yesterday_start,
        period_end=today_start,
    )

    # Get real-time metrics
    realtime = await query_service.get_realtime_metrics(workspace_id)

    # Get rollups for dispatch time
    rollups = await query_service.get_rollups(
        workspace_id=workspace_id,
        rollup_key="message.dispatch.duration",
        granularity=RollupGranularity.HOUR_1,
        start_time=start_time,
        end_time=end_time,
    )

    avg_dispatch_ms = 0.0
    if rollups:
        total = sum(r.duration_avg or 0 for r in rollups)
        avg_dispatch_ms = total / len(rollups)

    return DashboardSummaryResponse(
        workspace_id=workspace_id,
        period=period,
        messages_sent_today=today_metrics.messages_sent if today_metrics else 0,
        messages_sent_yesterday=yesterday_metrics.messages_sent if yesterday_metrics else 0,
        campaigns_active=realtime.active_campaigns if realtime else 0,
        campaigns_completed_today=today_metrics.campaigns_completed if today_metrics else 0,
        delivery_rate=(today_metrics.message_delivery_rate or 0) if today_metrics else 0,
        avg_dispatch_time_ms=avg_dispatch_ms,
        queue_depth=realtime.queue_depth if realtime else 0,
        error_rate=realtime.error_rate_percent if realtime else 0,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Metrics Routes
# ─────────────────────────────────────────────────────────────────────────────

@events_router.get("/campaign/{campaign_id}", response_model=CampaignMetricsResponse)
async def get_campaign_metrics(
    campaign_id: int,
    user=Depends(get_current_user),
) -> CampaignMetricsResponse:
    """
    Get metrics for a specific campaign.

    Args:
        campaign_id: Campaign ID

    Returns:
        Campaign metrics
    """
    query_service = AnalyticsQueryService()
    metrics = await query_service.get_campaign_metrics(campaign_id)

    if metrics is None:
        raise HTTPException(status_code=404, detail="Campaign metrics not found")

    return CampaignMetricsResponse(
        campaign_id=metrics.campaign_id,
        workspace_id=metrics.workspace_id,
        total_recipients=metrics.total_recipients,
        sent_count=metrics.sent_count,
        delivered_count=metrics.delivered_count,
        read_count=metrics.read_count,
        failed_count=metrics.failed_count,
        delivery_rate=metrics.delivery_rate,
        read_rate=metrics.read_rate,
        failure_rate=metrics.failure_rate,
        avg_per_recipient_ms=metrics.avg_per_recipient_ms,
        recovery_count=metrics.recovery_count,
        final_status=metrics.final_status,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Real-time Metrics Routes
# ─────────────────────────────────────────────────────────────────────────────

@events_router.get("/realtime", response_model=RealtimeMetricsResponse)
async def get_realtime_metrics(
    workspace_id: int,
    user=Depends(get_current_user),
) -> RealtimeMetricsResponse:
    """
    Get real-time metrics for a workspace.

    Args:
        workspace_id: Workspace ID

    Returns:
        Real-time metrics
    """
    query_service = AnalyticsQueryService()
    metrics = await query_service.get_realtime_metrics(workspace_id)

    if metrics is None:
        # Return default metrics
        return RealtimeMetricsResponse(
            workspace_id=workspace_id,
            active_campaigns=0,
            messages_in_flight=0,
            queue_depth=0,
            active_workers=0,
            messages_last_minute=0,
            messages_last_hour=0,
            messages_per_second=None,
            avg_queue_latency_ms=None,
            avg_dispatch_latency_ms=None,
            p95_dispatch_latency_ms=None,
            error_rate_percent=None,
            updated_at=datetime.now(timezone.utc),
        )

    return RealtimeMetricsResponse(
        workspace_id=metrics.workspace_id,
        active_campaigns=metrics.active_campaigns,
        messages_in_flight=metrics.messages_in_flight,
        queue_depth=metrics.queue_depth,
        active_workers=metrics.active_workers,
        messages_last_minute=metrics.messages_last_minute,
        messages_last_hour=metrics.messages_last_hour,
        messages_per_second=metrics.messages_per_second,
        avg_queue_latency_ms=metrics.avg_queue_latency_ms,
        avg_dispatch_latency_ms=metrics.avg_dispatch_latency_ms,
        p95_dispatch_latency_ms=metrics.p95_dispatch_latency_ms,
        error_rate_percent=metrics.error_rate_percent,
        updated_at=metrics.updated_at,
    )


@events_router.post("/realtime/update")
async def update_realtime_metrics(
    workspace_id: int,
    active_campaigns: int | None = None,
    messages_in_flight: int | None = None,
    queue_depth: int | None = None,
    active_workers: int | None = None,
    messages_per_second: float | None = None,
    avg_dispatch_latency_ms: float | None = None,
    error_rate_percent: float | None = None,
    user=Depends(get_current_user),
) -> dict[str, str]:
    """
    Update real-time metrics.

    Args:
        workspace_id: Workspace ID
        Various metric values to update

    Returns:
        Status message
    """
    realtime_service = RealtimeMetricsService()

    update_data = {}
    if active_campaigns is not None:
        update_data["active_campaigns"] = active_campaigns
    if messages_in_flight is not None:
        update_data["messages_in_flight"] = messages_in_flight
    if queue_depth is not None:
        update_data["queue_depth"] = queue_depth
    if active_workers is not None:
        update_data["active_workers"] = active_workers
    if messages_per_second is not None:
        update_data["messages_per_second"] = messages_per_second
    if avg_dispatch_latency_ms is not None:
        update_data["avg_dispatch_latency_ms"] = avg_dispatch_latency_ms
    if error_rate_percent is not None:
        update_data["error_rate_percent"] = error_rate_percent

    await realtime_service.update_realtime(workspace_id, **update_data)

    return {"status": "updated"}


# ─────────────────────────────────────────────────────────────────────────────
# Event Ingestion Routes (Internal)
# ─────────────────────────────────────────────────────────────────────────────

class EventIngestionRequest(BaseModel):
    """Request to ingest an analytics event."""

    event_type: str
    workspace_id: int
    occurred_at: datetime | None = None
    campaign_id: int | None = None
    user_id: int | None = None
    contact_id: int | None = None
    queue_name: str | None = None
    task_id: str | None = None
    worker_id: str | None = None
    duration_ms: float | None = None
    success: bool = True
    error_type: str | None = None
    trace_id: str | None = None
    labels: dict | None = None
    event_data: dict | None = None


@events_router.post("/ingest")
async def ingest_event(
    request: EventIngestionRequest,
) -> dict[str, str]:
    """
    Ingest an analytics event.

    This endpoint is for internal use by services.
    External clients should use the event-specific endpoints.

    Args:
        request: Event data

    Returns:
        Status message with event ID
    """
    ingestion_service = AnalyticsIngestionService()

    event = await ingestion_service.ingest_event(
        event_type=request.event_type,
        workspace_id=request.workspace_id,
        occurred_at=request.occurred_at,
        campaign_id=request.campaign_id,
        user_id=request.user_id,
        contact_id=request.contact_id,
        queue_name=request.queue_name,
        task_id=request.task_id,
        worker_id=request.worker_id,
        duration_ms=request.duration_ms,
        success=request.success,
        error_type=request.error_type,
        trace_id=request.trace_id,
        labels=request.labels,
        event_data=request.event_data,
    )

    return {
        "status": "ingested",
        "event_id": str(event.event_id),
    }


class BatchIngestionRequest(BaseModel):
    """Request to ingest multiple analytics events."""

    events: list[EventIngestionRequest]


@events_router.post("/ingest/batch")
async def ingest_batch(
    request: BatchIngestionRequest,
) -> dict[str, Any]:
    """
    Ingest multiple analytics events.

    Args:
        request: Batch of events

    Returns:
        Status with count
    """
    ingestion_service = AnalyticsIngestionService()

    events_data = [event.model_dump() for event in request.events]
    events = await ingestion_service.ingest_batch(events_data)

    return {
        "status": "ingested",
        "count": len(events),
    }
