"""
Dashboard query schemas for ChatPulse analytics.

Provides comprehensive DTOs for:
- Campaign delivery metrics
- Workspace usage metrics
- Queue health metrics
- Webhook health metrics
- Retry analytics
- Recovery analytics
"""

from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


# ─────────────────────────────────────────────────────────────────────────────
# Enums
# ─────────────────────────────────────────────────────────────────────────────

class TimeGranularity(str, Enum):
    """Time granularity for aggregations."""

    MINUTE = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR = "1h"
    DAY = "1d"
    WEEK = "1w"


class MetricPeriod(str, Enum):
    """Predefined metric periods."""

    TODAY = "today"
    YESTERDAY = "yesterday"
    LAST_7_DAYS = "last_7_days"
    LAST_30_DAYS = "last_30_days"
    LAST_90_DAYS = "last_90_days"
    THIS_MONTH = "this_month"
    LAST_MONTH = "last_month"


class TrendDirection(str, Enum):
    """Trend direction indicators."""

    UP = "up"
    DOWN = "down"
    STABLE = "stable"


# ─────────────────────────────────────────────────────────────────────────────
# Pagination & Filtering
# ─────────────────────────────────────────────────────────────────────────────

class PaginationParams(BaseModel):
    """Pagination parameters."""

    limit: int = Field(default=50, ge=1, le=1000)
    offset: int = Field(default=0, ge=0)
    cursor: str | None = None


class DateRangeParams(BaseModel):
    """Date range parameters."""

    start_time: datetime | None = None
    end_time: datetime | None = None
    period: MetricPeriod | None = None


class DashboardFilters(BaseModel):
    """Common dashboard filters."""

    workspace_id: int | None = None
    campaign_id: int | None = None
    event_types: list[str] | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    granularity: TimeGranularity = TimeGranularity.HOUR
    tags: list[str] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Base Response Models
# ─────────────────────────────────────────────────────────────────────────────

class TrendInfo(BaseModel):
    """Trend information for a metric."""

    current: float
    previous: float | None = None
    change: float | None = None
    change_percent: float | None = None
    direction: TrendDirection | None = None


class PaginatedResponse(BaseModel):
    """Paginated response wrapper."""

    items: list[Any]
    total: int
    limit: int
    offset: int
    has_more: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Delivery Metrics
# ─────────────────────────────────────────────────────────────────────────────

class CampaignDeliverySummary(BaseModel):
    """Campaign delivery summary."""

    campaign_id: int
    workspace_id: int
    campaign_name: str | None = None

    total_recipients: int
    sent_count: int
    delivered_count: int
    read_count: int
    failed_count: int
    pending_count: int

    delivery_rate: float
    read_rate: float
    failure_rate: float

    avg_time_to_deliver_ms: float | None = None
    avg_time_to_read_ms: float | None = None


class CampaignDeliveryTimeline(BaseModel):
    """Time series data for campaign delivery."""

    timestamp: datetime
    sent: int = 0
    delivered: int = 0
    read: int = 0
    failed: int = 0


class CampaignDeliveryResponse(BaseModel):
    """Campaign delivery metrics response."""

    summary: CampaignDeliverySummary
    timeline: list[CampaignDeliveryTimeline] = []
    by_hour: dict[str, int] = {}
    error_breakdown: dict[str, int] = {}

    start_time: datetime
    end_time: datetime
    duration_seconds: float | None = None


class CampaignDeliveryListResponse(PaginatedResponse):
    """List of campaign delivery metrics."""

    items: list[CampaignDeliverySummary]


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Usage Metrics
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceUsageSummary(BaseModel):
    """Workspace usage summary."""

    workspace_id: int
    period: str

    # Message metrics
    messages_sent: int
    messages_delivered: int
    messages_failed: int
    messages_read: int
    delivery_rate: float
    read_rate: float
    failure_rate: float

    # Campaign metrics
    campaigns_created: int
    campaigns_completed: int
    campaigns_failed: int
    campaigns_active: int

    # Contact metrics
    contacts_added: int
    contacts_total: int
    segments_created: int

    # API metrics
    api_requests: int
    api_errors: int
    avg_response_time_ms: float | None = None

    # Trend data
    messages_trend: TrendInfo | None = None
    campaigns_trend: TrendInfo | None = None


class WorkspaceUsageTimeline(BaseModel):
    """Time series data for workspace usage."""

    timestamp: datetime
    messages_sent: int = 0
    messages_delivered: int = 0
    api_requests: int = 0
    active_campaigns: int = 0


class WorkspaceUsageResponse(BaseModel):
    """Workspace usage metrics response."""

    summary: WorkspaceUsageSummary
    timeline: list[WorkspaceUsageTimeline] = []
    top_campaigns: list[CampaignDeliverySummary] = []
    by_day: dict[str, int] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Queue Health Metrics
# ─────────────────────────────────────────────────────────────────────────────

class QueueHealthSummary(BaseModel):
    """Queue health summary."""

    workspace_id: int
    queue_name: str

    tasks_pending: int
    tasks_in_progress: int
    tasks_completed: int
    tasks_failed: int
    tasks_retried: int

    success_rate: float
    failure_rate: float
    retry_rate: float

    avg_queue_time_ms: float | None = None
    avg_process_time_ms: float | None = None
    p95_process_time_ms: float | None = None
    p99_process_time_ms: float | None = None

    queue_depth: int
    active_workers: int


class QueueHealthTimeline(BaseModel):
    """Time series data for queue health."""

    timestamp: datetime
    queue_depth: int = 0
    tasks_completed: int = 0
    tasks_failed: int = 0
    active_workers: int = 0


class QueueHealthResponse(BaseModel):
    """Queue health metrics response."""

    summary: QueueHealthSummary
    timeline: list[QueueHealthTimeline] = []
    error_breakdown: dict[str, int] = {}
    by_worker: dict[str, int] = {}


class QueueHealthListResponse(PaginatedResponse):
    """List of queue health metrics."""

    items: list[QueueHealthSummary]


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Health Metrics
# ─────────────────────────────────────────────────────────────────────────────

class WebhookHealthSummary(BaseModel):
    """Webhook health summary."""

    workspace_id: int

    webhooks_received: int
    webhooks_processed: int
    webhooks_failed: int
    webhooks_pending: int

    success_rate: float
    failure_rate: float

    avg_process_time_ms: float | None = None
    p95_process_time_ms: float | None = None
    p99_process_time_ms: float | None = None

    by_source: dict[str, int] = {}
    error_breakdown: dict[str, int] = {}


class WebhookHealthTimeline(BaseModel):
    """Time series data for webhook health."""

    timestamp: datetime
    received: int = 0
    processed: int = 0
    failed: int = 0


class WebhookHealthResponse(BaseModel):
    """Webhook health metrics response."""

    summary: WebhookHealthSummary
    timeline: list[WebhookHealthTimeline] = []
    recent_failures: list[WebhookFailureDetail] = []


class WebhookFailureDetail(BaseModel):
    """Webhook failure details."""

    webhook_id: int
    source: str
    error_type: str
    error_message: str | None = None
    received_at: datetime
    retry_count: int


# ─────────────────────────────────────────────────────────────────────────────
# Retry Analytics
# ─────────────────────────────────────────────────────────────────────────────

class RetryAnalyticsSummary(BaseModel):
    """Retry analytics summary."""

    workspace_id: int

    total_retries: int
    retry_success_count: int
    retry_failure_count: int

    retry_rate: float
    retry_success_rate: float

    avg_retry_delay_ms: float | None = None
    max_retry_attempts: int

    by_error_type: dict[str, int] = {}
    by_campaign: dict[int, int] = {}


class RetryAnalyticsTimeline(BaseModel):
    """Time series data for retry analytics."""

    timestamp: datetime
    retry_attempts: int = 0
    retry_successes: int = 0
    retry_failures: int = 0


class RetryAnalyticsResponse(BaseModel):
    """Retry analytics response."""

    summary: RetryAnalyticsSummary
    timeline: list[RetryAnalyticsTimeline] = []
    top_retry_error_types: list[ErrorTypeBreakdown] = []


class ErrorTypeBreakdown(BaseModel):
    """Breakdown by error type."""

    error_type: str
    count: int
    retry_rate: float
    success_after_retry: float


# ─────────────────────────────────────────────────────────────────────────────
# Recovery Analytics
# ─────────────────────────────────────────────────────────────────────────────

class RecoveryAnalyticsSummary(BaseModel):
    """Recovery analytics summary."""

    workspace_id: int

    recoveries_detected: int
    recoveries_started: int
    recoveries_completed: int
    recoveries_failed: int

    recovered_messages: int
    recovered_campaigns: int

    recovery_rate: float
    success_rate: float

    avg_recovery_time_ms: float | None = None
    avg_messages_recovered: float | None = None


class RecoveryAnalyticsTimeline(BaseModel):
    """Time series data for recovery analytics."""

    timestamp: datetime
    detected: int = 0
    started: int = 0
    completed: int = 0
    failed: int = 0


class RecoveryAnalyticsResponse(BaseModel):
    """Recovery analytics response."""

    summary: RecoveryAnalyticsSummary
    timeline: list[RecoveryAnalyticsTimeline] = []
    recent_recoveries: list[RecoveryDetail] = []


class RecoveryDetail(BaseModel):
    """Recovery operation details."""

    recovery_id: int
    campaign_id: int
    status: str
    detected_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None

    messages_to_recover: int
    messages_recovered: int
    recovery_attempts: int


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Overview
# ─────────────────────────────────────────────────────────────────────────────

class DashboardOverview(BaseModel):
    """Overall dashboard overview."""

    workspace_id: int
    generated_at: datetime

    period: str
    period_start: datetime
    period_end: datetime

    # Summary metrics
    total_messages_sent: int
    total_messages_delivered: int
    total_campaigns: int
    campaigns_completed: int
    campaigns_active: int

    # Rates
    delivery_rate: float
    read_rate: float
    error_rate: float

    # Performance
    avg_dispatch_time_ms: float | None = None
    queue_depth: int
    active_workers: int

    # Health scores (0-100)
    health_score: float | None = None
    delivery_health: float | None = None
    queue_health: float | None = None
    webhook_health: float | None = None


class DashboardComparison(BaseModel):
    """Period comparison data."""

    current_period: DashboardOverview
    previous_period: DashboardOverview
    changes: dict[str, float] = {}


# ─────────────────────────────────────────────────────────────────────────────
# Real-time Dashboard
# ─────────────────────────────────────────────────────────────────────────────

class RealtimeCampaignStatus(BaseModel):
    """Real-time campaign status."""

    campaign_id: int
    campaign_name: str | None = None
    status: str
    progress_percent: float

    total_recipients: int
    sent_count: int
    delivered_count: int
    failed_count: int

    messages_per_second: float
    eta_seconds: int | None = None

    updated_at: datetime


class RealtimeQueueStatus(BaseModel):
    """Real-time queue status."""

    queue_name: str
    queue_depth: int
    active_workers: int
    avg_wait_time_ms: float | None = None
    messages_per_second: float


class RealtimeDashboardResponse(BaseModel):
    """Real-time dashboard response."""

    workspace_id: int
    updated_at: datetime

    messages_in_flight: int
    messages_per_second: float

    active_campaigns: list[RealtimeCampaignStatus] = []
    active_queues: list[RealtimeQueueStatus] = []

    alerts: list[DashboardAlert] = []


class DashboardAlert(BaseModel):
    """Dashboard alert."""

    alert_id: str
    severity: str  # info, warning, error, critical
    message: str
    metric_name: str
    current_value: float
    threshold: float
    created_at: datetime


# ─────────────────────────────────────────────────────────────────────────────
# Query Request Models
# ─────────────────────────────────────────────────────────────────────────────

class CampaignDeliveryRequest(DashboardFilters):
    """Request for campaign delivery metrics."""

    campaign_id: int | None = None
    include_timeline: bool = True
    include_error_breakdown: bool = True
    granularity: TimeGranularity = TimeGranularity.HOUR


class WorkspaceUsageRequest(DashboardFilters):
    """Request for workspace usage metrics."""

    include_timeline: bool = True
    include_top_campaigns: bool = True
    granularity: TimeGranularity = TimeGranularity.DAY


class QueueHealthRequest(DashboardFilters):
    """Request for queue health metrics."""

    queue_name: str | None = None
    include_timeline: bool = True
    include_worker_breakdown: bool = True


class WebhookHealthRequest(DashboardFilters):
    """Request for webhook health metrics."""

    include_timeline: bool = True
    include_recent_failures: bool = True
    limit_recent_failures: int = 10


class RetryAnalyticsRequest(DashboardFilters):
    """Request for retry analytics."""

    campaign_id: int | None = None
    include_timeline: bool = True


class RecoveryAnalyticsRequest(DashboardFilters):
    """Request for recovery analytics."""

    campaign_id: int | None = None
    include_timeline: bool = True
    include_recent_recoveries: bool = True
    limit_recent_recoveries: int = 10


class DashboardOverviewRequest(BaseModel):
    """Request for dashboard overview."""

    workspace_id: int
    period: MetricPeriod = MetricPeriod.TODAY
    compare_previous: bool = False


class RealtimeDashboardRequest(BaseModel):
    """Request for real-time dashboard."""

    workspace_id: int
    include_campaigns: bool = True
    include_queues: bool = True
    alert_threshold: float = 0.8