"""
Dashboard analytics API routes.

Provides comprehensive analytics endpoints for:
- Campaign delivery metrics
- Workspace usage metrics
- Queue health metrics
- Webhook health metrics
- Retry analytics
- Recovery analytics
- Dashboard overview
- Real-time updates (SSE)

All endpoints support:
- Pagination
- Date range filtering
- Aggregation granularity
- Caching with stale-while-revalidate
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sse_starlette.sse import EventSourceResponse

from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.dashboard import (
    DashboardOverview,
    PaginationParams,
    QueueHealthResponse,
    RealtimeDashboardResponse,
    RecoveryAnalyticsResponse,
    RetryAnalyticsResponse,
    WebhookHealthResponse,
    WorkspaceUsageResponse,
)
from app.services.dashboard.query_service import DashboardQueryService
from app.services.dashboard.realtime import (
    Channel,
    EventKind,
    get_realtime_service,
)
from app.services.dashboard.query_builder import PaginationInput

router = APIRouter(prefix="/dashboard", tags=["Dashboard Analytics"])


# ─────────────────────────────────────────────────────────────────────────────
# Dependencies
# ─────────────────────────────────────────────────────────────────────────────


def get_dashboard_service() -> DashboardQueryService:
    """Get dashboard query service instance."""
    return DashboardQueryService()


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Delivery Metrics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/campaigns/{campaign_id}/delivery")
async def get_campaign_delivery_metrics(
    campaign_id: int,
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    granularity: str = Query(default="1h"),
    include_timeline: bool = Query(default=True),
    include_error_breakdown: bool = Query(default=True),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get delivery metrics for a specific campaign.

    Includes summary stats, timeline, and error breakdown.
    """
    pagination = PaginationInput(limit=limit, offset=offset)

    return await service.get_campaign_delivery(
        workspace_id=workspace.id,
        campaign_id=campaign_id,
        start_time=start_time,
        end_time=end_time,
        period=period,
        granularity=granularity,
        include_timeline=include_timeline,
        include_error_breakdown=include_error_breakdown,
        pagination=pagination,
    )


@router.get("/campaigns/delivery")
async def list_campaign_delivery_metrics(
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    limit: int = Query(default=50, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    sort_by: str = Query(default="created_at"),
    sort_dir: str = Query(default="desc"),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    List all campaigns with delivery metrics.

    Supports pagination and sorting.
    """
    pagination = PaginationInput(limit=limit, offset=offset)

    return await service.get_campaign_delivery_list(
        workspace_id=workspace.id,
        start_time=start_time,
        end_time=end_time,
        period=period,
        pagination=pagination,
        sort_by=sort_by,
        sort_dir=sort_dir,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Usage Metrics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/workspace/usage")
async def get_workspace_usage_metrics(
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    granularity: str = Query(default="1d"),
    include_timeline: bool = Query(default=True),
    include_top_campaigns: bool = Query(default=True),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get workspace usage metrics.

    Includes message counts, campaign stats, contact metrics.
    """
    return await service.get_workspace_usage(
        workspace_id=workspace.id,
        start_time=start_time,
        end_time=end_time,
        period=period,
        granularity=granularity,
        include_timeline=include_timeline,
        include_top_campaigns=include_top_campaigns,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Queue Health Metrics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/queue/health")
async def get_queue_health_metrics(
    queue_name: str | None = Query(None),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    include_timeline: bool = Query(default=True),
    include_worker_breakdown: bool = Query(default=True),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get queue health metrics.

    Shows task processing rates, failure rates, worker distribution.
    """
    return await service.get_queue_health(
        workspace_id=workspace.id,
        queue_name=queue_name,
        start_time=start_time,
        end_time=end_time,
        period=period,
        include_timeline=include_timeline,
        include_worker_breakdown=include_worker_breakdown,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Health Metrics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/webhooks/health")
async def get_webhook_health_metrics(
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    include_timeline: bool = Query(default=True),
    include_recent_failures: bool = Query(default=True),
    limit_recent_failures: int = Query(default=10, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get webhook health metrics.

    Shows webhook processing rates, failure rates, recent failures.
    """
    return await service.get_webhook_health(
        workspace_id=workspace.id,
        start_time=start_time,
        end_time=end_time,
        period=period,
        include_timeline=include_timeline,
        include_recent_failures=include_recent_failures,
        limit_recent_failures=limit_recent_failures,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Retry Analytics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/analytics/retry")
async def get_retry_analytics_metrics(
    campaign_id: int | None = Query(None),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    include_timeline: bool = Query(default=True),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get retry analytics.

    Shows retry rates, success rates, error breakdowns.
    """
    return await service.get_retry_analytics(
        workspace_id=workspace.id,
        campaign_id=campaign_id,
        start_time=start_time,
        end_time=end_time,
        period=period,
        include_timeline=include_timeline,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Recovery Analytics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/analytics/recovery")
async def get_recovery_analytics_metrics(
    campaign_id: int | None = Query(None),
    start_time: datetime | None = Query(None),
    end_time: datetime | None = Query(None),
    period: str | None = Query(None),
    include_timeline: bool = Query(default=True),
    include_recent_recoveries: bool = Query(default=True),
    limit_recent_recoveries: int = Query(default=10, ge=1, le=100),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get recovery analytics.

    Shows recovery rates, recovered message counts.
    """
    return await service.get_recovery_analytics(
        workspace_id=workspace.id,
        campaign_id=campaign_id,
        start_time=start_time,
        end_time=end_time,
        period=period,
        include_timeline=include_timeline,
        include_recent_recoveries=include_recent_recoveries,
        limit_recent_recoveries=limit_recent_recoveries,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Overview
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/overview")
async def get_dashboard_overview(
    period: str = Query(default="today"),
    compare_previous: bool = Query(default=False),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get dashboard overview.

    Returns summary metrics with optional period comparison.
    """
    return await service.get_dashboard_overview(
        workspace_id=workspace.id,
        period=period,
        compare_previous=compare_previous,
    )


@router.get("/alerts")
async def get_dashboard_alerts(
    severity_threshold: str = Query(default="warning"),
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> list[dict[str, Any]]:
    """
    Get active dashboard alerts.

    Returns alerts based on metric thresholds.
    """
    return await service.get_alerts(
        workspace_id=workspace.id,
        severity_threshold=severity_threshold,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Real-time Metrics
# ─────────────────────────────────────────────────────────────────────────────


@router.get("/realtime")
async def get_realtime_metrics(
    workspace: Workspace = Depends(get_current_workspace),
    service: DashboardQueryService = Depends(get_dashboard_service),
) -> dict[str, Any]:
    """
    Get real-time metrics.

    Returns current active campaigns, messages in flight, rates.
    """
    return await service.get_realtime_metrics(
        workspace_id=workspace.id,
    )


@router.get("/realtime/stream")
async def stream_realtime_metrics(
    workspace: Workspace = Depends(get_current_workspace),
) -> EventSourceResponse:
    """
    Stream real-time metrics via Server-Sent Events.

    Subscribe to workspace channel for live updates.
    Returns SSE stream with:
    - metric.update events
    - campaign.progress events
    - alert events
    - heartbeat events
    """
    realtime = get_realtime_service()
    workspace_id = workspace.id

    async def event_generator():
        channel = Channel.workspace(workspace_id)
        r = await realtime._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)

        try:
            last_heartbeat = datetime.now(timezone.utc)

            async for raw in pubsub.listen():
                if raw["type"] == "message":
                    try:
                        msg_json = raw["data"]
                        data = json.loads(msg_json)
                        kind = data.get("kind", "metric.update")
                        yield {
                            "event": kind,
                            "data": msg_json,
                        }
                    except Exception:
                        pass

                # Heartbeat every 30 seconds
                now = datetime.now(timezone.utc)
                if (now - last_heartbeat).total_seconds() >= 30:
                    yield {
                        "event": "heartbeat",
                        "data": json.dumps({"timestamp": now.isoformat()}),
                    }
                    last_heartbeat = now

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    return EventSourceResponse(event_generator())


# ─────────────────────────────────────────────────────────────────────────────
# Cache Management
# ─────────────────────────────────────────────────────────────────────────────


@router.post("/cache/invalidate")
async def invalidate_dashboard_cache(
    metric_type: str | None = Query(None),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """
    Invalidate dashboard cache.

    If metric_type is specified, only that type is invalidated.
    Otherwise, all workspace cache is cleared.
    """
    from app.services.dashboard.cache import get_dashboard_cache

    cache = get_dashboard_cache()

    if metric_type:
        count = await cache.invalidate_metric_type(metric_type)
    else:
        count = await cache.invalidate_workspace(workspace.id)

    return {
        "status": "invalidated",
        "keys_cleared": count,
        "workspace_id": workspace.id,
    }


@router.get("/cache/stats")
async def get_cache_stats(
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, Any]:
    """Get dashboard cache statistics."""
    from app.services.dashboard.cache import get_dashboard_cache

    cache = get_dashboard_cache()
    stats = await cache.get_stats()
    return {
        "workspace_id": workspace.id,
        **stats,
    }
