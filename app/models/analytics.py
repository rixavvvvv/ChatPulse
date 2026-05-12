"""
Analytics models for ChatPulse.

Provides:
- analytics_events: Append-only event log
- analytics_rollups: Pre-computed aggregated metrics
- workspace_metrics: Per-workspace aggregated metrics
- campaign_metrics: Per-campaign aggregated metrics
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    String,
    Text,
    BigInteger,
    ForeignKey,
    JSON,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship

from app.db import Base


# ─────────────────────────────────────────────────────────────────────────────
# Event Types
# ─────────────────────────────────────────────────────────────────────────────

class EventType(str, Enum):
    """Analytics event types."""

    # Message events
    MESSAGE_SENT = "message.sent"
    MESSAGE_DELIVERED = "message.delivered"
    MESSAGE_FAILED = "message.failed"
    MESSAGE_READ = "message.read"

    # Webhook events
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"
    WEBHOOK_FAILED = "webhook.failed"

    # Campaign events
    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_STARTED = "campaign.started"
    CAMPAIGN_COMPLETED = "campaign.completed"
    CAMPAIGN_FAILED = "campaign.failed"
    CAMPAIGN_PAUSED = "campaign.paused"
    CAMPAIGN_RESUMED = "campaign.resumed"

    # Recovery events
    RECOVERY_DETECTED = "recovery.detected"
    RECOVERY_STARTED = "recovery.started"
    RECOVERY_COMPLETED = "recovery.completed"
    RECOVERY_FAILED = "recovery.failed"

    # Rate limit events
    RATE_LIMIT_ALLOWED = "rate_limit.allowed"
    RATE_LIMIT_REJECTED = "rate_limit.rejected"

    # API events
    API_REQUEST = "api.request"
    API_ERROR = "api.error"

    # Queue events
    QUEUE_TASK_STARTED = "queue.task.started"
    QUEUE_TASK_COMPLETED = "queue.task.completed"
    QUEUE_TASK_FAILED = "queue.task.failed"

    # Segment events
    SEGMENT_CREATED = "segment.created"
    SEGMENT_UPDATED = "segment.updated"
    SEGMENT_DELETED = "segment.deleted"
    SEGMENT_CONTACTS_ADDED = "segment.contacts.added"
    SEGMENT_CONTACTS_REMOVED = "segment.contacts.removed"

    # Contact events
    CONTACT_CREATED = "contact.created"
    CONTACT_UPDATED = "contact.updated"
    CONTACT_TAGGED = "contact.tagged"
    CONTACT_UNTAGGED = "contact.untagged"

    # User events
    USER_LOGIN = "user.login"
    USER_LOGOUT = "user.logout"
    USER_API_KEY_CREATED = "user.api_key.created"
    USER_API_KEY_REVOKED = "user.api_key.revoked"


class EventCategory(str, Enum):
    """Event categories for grouping."""

    MESSAGE = "message"
    WEBHOOK = "webhook"
    CAMPAIGN = "campaign"
    RECOVERY = "recovery"
    RATE_LIMIT = "rate_limit"
    API = "api"
    QUEUE = "queue"
    SEGMENT = "segment"
    CONTACT = "contact"
    USER = "user"


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Events (Append-Only Event Log)
# ─────────────────────────────────────────────────────────────────────────────

class AnalyticsEvent(Base):
    """
    Append-only analytics event log.

    This is the primary source of truth for all analytics data.
    Events are immutable once written.

    Partitioned by date for efficient querying and retention management.
    """

    __tablename__ = "analytics_events"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    event_id = Column(UUID(as_uuid=True), unique=True, nullable=False, index=True)

    # Event classification
    event_type = Column(String(100), nullable=False, index=True)
    event_category = Column(String(50), nullable=False, index=True)

    # Temporal data
    occurred_at = Column(DateTime(timezone=True), nullable=False, index=True)
    ingested_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))

    # Resource identifiers
    workspace_id = Column(Integer, nullable=False, index=True)
    campaign_id = Column(Integer, nullable=True, index=True)
    user_id = Column(Integer, nullable=True)
    contact_id = Column(Integer, nullable=True)
    queue_name = Column(String(100), nullable=True)
    task_id = Column(String(100), nullable=True)
    worker_id = Column(String(100), nullable=True)

    # Event data (JSON for flexibility)
    event_data = Column(JSON, nullable=False, default=dict)

    # Numeric metrics captured at event time
    value_numeric = Column(Float, nullable=True)
    duration_ms = Column(Float, nullable=True)
    count = Column(Integer, nullable=True)

    # Source tracking
    source = Column(String(100), nullable=True, index=True)
    trace_id = Column(String(50), nullable=True, index=True)
    request_id = Column(String(100), nullable=True)

    # Event outcome
    success = Column(Boolean, nullable=True)
    error_type = Column(String(100), nullable=True)

    # Labels for dimensional analysis
    labels = Column(JSON, nullable=True)

    # Processing status
    processed = Column(Boolean, default=False, index=True)
    processed_at = Column(DateTime(timezone=True), nullable=True)
    aggregation_key = Column(String(200), nullable=True, index=True)

    __table_args__ = (
        # Composite indexes for common queries
        Index("ix_analytics_events_workspace_time", "workspace_id", "occurred_at"),
        Index("ix_analytics_events_campaign_time", "campaign_id", "occurred_at"),
        Index("ix_analytics_events_category_time", "event_category", "occurred_at"),
        Index("ix_analytics_events_type_workspace", "event_type", "workspace_id"),
        Index("ix_analytics_events_workspace_category_processed", "workspace_id", "event_category", "processed"),
        Index("ix_analytics_events_occurred_processed", "occurred_at", "processed"),
    )

    def __repr__(self) -> str:
        return f"<AnalyticsEvent(id={self.id}, type={self.event_type}, workspace={self.workspace_id})>"


# ─────────────────────────────────────────────────────────────────────────────
# Analytics Rollups (Pre-computed Aggregations)
# ─────────────────────────────────────────────────────────────────────────────

class RollupGranularity(str, Enum):
    """Rollup time granularity."""

    MINUTE_1 = "1m"
    MINUTE_5 = "5m"
    MINUTE_15 = "15m"
    HOUR_1 = "1h"
    DAY_1 = "1d"
    WEEK_1 = "1w"


class AnalyticsRollup(Base):
    """
    Pre-computed aggregated metrics.

    These are materialized aggregations from analytics_events.
    Updated by periodic aggregation workers.
    """

    __tablename__ = "analytics_rollups"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Rollup identity
    workspace_id = Column(Integer, nullable=False, index=True)
    rollup_key = Column(String(200), nullable=False, index=True)
    granularity = Column(String(10), nullable=False)

    # Time window
    window_start = Column(DateTime(timezone=True), nullable=False, index=True)
    window_end = Column(DateTime(timezone=True), nullable=False)

    # Event classification for this rollup
    event_type = Column(String(100), nullable=False, index=True)
    event_category = Column(String(50), nullable=True)

    # Aggregated metrics
    total_count = Column(BigInteger, nullable=False, default=0)
    success_count = Column(BigInteger, nullable=False, default=0)
    failure_count = Column(BigInteger, nullable=False, default=0)

    # Numeric aggregations
    value_sum = Column(Float, nullable=False, default=0)
    value_min = Column(Float, nullable=True)
    value_max = Column(Float, nullable=True)
    value_avg = Column(Float, nullable=True)

    # Duration aggregations
    duration_sum = Column(Float, nullable=False, default=0)
    duration_min = Column(Float, nullable=True)
    duration_max = Column(Float, nullable=True)
    duration_avg = Column(Float, nullable=True)
    duration_p50 = Column(Float, nullable=True)
    duration_p95 = Column(Float, nullable=True)
    duration_p99 = Column(Float, nullable=True)

    # Unique counts
    unique_contacts = Column(BigInteger, nullable=True)
    unique_campaigns = Column(BigInteger, nullable=True)
    unique_users = Column(BigInteger, nullable=True)

    # Dimensional labels
    labels = Column(JSON, nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_rollups_workspace_granularity_window", "workspace_id", "granularity", "window_start"),
        Index("ix_rollups_key_granularity_window", "rollup_key", "granularity", "window_start"),
        Index("ix_rollups_event_type_window", "event_type", "window_start"),
    )

    def __repr__(self) -> str:
        return f"<AnalyticsRollup(key={self.rollup_key}, granularity={self.granularity}, window={self.window_start})>"


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Metrics
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceMetrics(Base):
    """
    Per-workspace aggregated metrics.

    Provides current period metrics for dashboards and alerts.
    Updated in real-time and rolled up periodically.
    """

    __tablename__ = "workspace_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Workspace identity
    workspace_id = Column(Integer, unique=True, nullable=False, index=True)

    # Time periods
    period_start = Column(DateTime(timezone=True), nullable=False, index=True)
    period_end = Column(DateTime(timezone=True), nullable=False)

    # Message metrics
    messages_sent = Column(BigInteger, nullable=False, default=0)
    messages_delivered = Column(BigInteger, nullable=False, default=0)
    messages_failed = Column(BigInteger, nullable=False, default=0)
    message_delivery_rate = Column(Float, nullable=True)

    # Campaign metrics
    campaigns_created = Column(BigInteger, nullable=False, default=0)
    campaigns_completed = Column(BigInteger, nullable=False, default=0)
    campaigns_failed = Column(BigInteger, nullable=False, default=0)
    total_recipients = Column(BigInteger, nullable=False, default=0)

    # Contact metrics
    contacts_added = Column(BigInteger, nullable=False, default=0)
    contacts_updated = Column(BigInteger, nullable=False, default=0)
    contacts_total = Column(BigInteger, nullable=True)

    # Segment metrics
    segments_created = Column(BigInteger, nullable=False, default=0)
    segments_materialized = Column(BigInteger, nullable=False, default=0)

    # Webhook metrics
    webhooks_received = Column(BigInteger, nullable=False, default=0)
    webhooks_processed = Column(BigInteger, nullable=False, default=0)
    webhooks_failed = Column(BigInteger, nullable=False, default=0)

    # Recovery metrics
    recoveries_detected = Column(BigInteger, nullable=False, default=0)
    recoveries_completed = Column(BigInteger, nullable=False, default=0)
    recoveries_failed = Column(BigInteger, nullable=False, default=0)

    # Rate limit metrics
    rate_limit_allowed = Column(BigInteger, nullable=False, default=0)
    rate_limit_rejected = Column(BigInteger, nullable=False, default=0)

    # API metrics
    api_requests = Column(BigInteger, nullable=False, default=0)
    api_errors = Column(BigInteger, nullable=False, default=0)
    avg_response_time_ms = Column(Float, nullable=True)

    # Queue metrics
    tasks_started = Column(BigInteger, nullable=False, default=0)
    tasks_completed = Column(BigInteger, nullable=False, default=0)
    tasks_failed = Column(BigInteger, nullable=False, default=0)
    avg_task_duration_ms = Column(Float, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc))
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_workspace_metrics_period", "workspace_id", "period_start"),
    )

    def __repr__(self) -> str:
        return f"<WorkspaceMetrics(workspace={self.workspace_id}, period={self.period_start})>"


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Metrics
# ─────────────────────────────────────────────────────────────────────────────

class CampaignMetrics(Base):
    """
    Per-campaign aggregated metrics.

    Provides detailed metrics for campaign analysis and optimization.
    """

    __tablename__ = "campaign_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Campaign identity
    campaign_id = Column(Integer, unique=True, nullable=False, index=True)
    workspace_id = Column(Integer, nullable=False, index=True)

    # Campaign lifecycle
    created_at = Column(DateTime(timezone=True), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=True)
    completed_at = Column(DateTime(timezone=True), nullable=True)

    # Recipient metrics
    total_recipients = Column(Integer, nullable=False, default=0)
    sent_count = Column(Integer, nullable=False, default=0)
    delivered_count = Column(Integer, nullable=False, default=0)
    read_count = Column(Integer, nullable=False, default=0)
    failed_count = Column(Integer, nullable=False, default=0)

    # Computed rates
    delivery_rate = Column(Float, nullable=True)
    read_rate = Column(Float, nullable=True)
    failure_rate = Column(Float, nullable=True)

    # Duration metrics (in seconds)
    total_duration_seconds = Column(Float, nullable=True)
    avg_per_recipient_ms = Column(Float, nullable=True)
    min_recipient_ms = Column(Float, nullable=True)
    max_recipient_ms = Column(Float, nullable=True)

    # Hourly distribution
    hourly_counts = Column(JSON, nullable=True)  # {"0": 10, "1": 5, ...}

    # Error breakdown
    error_breakdown = Column(JSON, nullable=True)  # {"rate_limit": 5, "invalid_phone": 3, ...}

    # Recovery metrics
    recovery_count = Column(Integer, nullable=False, default=0)
    recovery_success_count = Column(Integer, nullable=False, default=0)
    last_recovery_at = Column(DateTime(timezone=True), nullable=True)

    # Throttle info
    throttle_wait_ms = Column(BigInteger, nullable=True)
    rate_limit_hits = Column(Integer, nullable=False, default=0)

    # Final state
    final_status = Column(String(50), nullable=True)
    termination_reason = Column(String(100), nullable=True)

    # Timestamps
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_campaign_metrics_workspace_time", "workspace_id", "created_at"),
    )

    def __repr__(self) -> str:
        return f"<CampaignMetrics(campaign={self.campaign_id}, sent={self.sent_count}/{self.total_recipients})>"


# ─────────────────────────────────────────────────────────────────────────────
# Realtime Metrics (High-frequency updates)
# ─────────────────────────────────────────────────────────────────────────────

class RealtimeMetrics(Base):
    """
    High-frequency real-time metrics for dashboards.

    These are updated in real-time (every few seconds) for live monitoring.
    Rolled up to permanent storage periodically.
    """

    __tablename__ = "realtime_metrics"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # Resource identifiers
    workspace_id = Column(Integer, nullable=False, index=True)
    campaign_id = Column(Integer, nullable=True, index=True)

    # Current state
    active_campaigns = Column(Integer, nullable=False, default=0)
    messages_in_flight = Column(Integer, nullable=False, default=0)
    queue_depth = Column(Integer, nullable=False, default=0)
    active_workers = Column(Integer, nullable=False, default=0)

    # Rolling counts (last minute/hour)
    messages_last_minute = Column(Integer, nullable=False, default=0)
    messages_last_hour = Column(BigInteger, nullable=False, default=0)
    webhooks_last_minute = Column(Integer, nullable=False, default=0)
    webhooks_last_hour = Column(BigInteger, nullable=False, default=0)

    # Rate metrics
    messages_per_second = Column(Float, nullable=True)
    webhooks_per_second = Column(Float, nullable=True)

    # Latency metrics (milliseconds)
    avg_queue_latency_ms = Column(Float, nullable=True)
    avg_dispatch_latency_ms = Column(Float, nullable=True)
    p95_dispatch_latency_ms = Column(Float, nullable=True)

    # Error rates
    error_rate_percent = Column(Float, nullable=True)

    # Updated timestamp
    updated_at = Column(DateTime(timezone=True), nullable=False, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("ix_realtime_metrics_workspace", "workspace_id", "updated_at"),
    )

    def __repr__(self) -> str:
        return f"<RealtimeMetrics(workspace={self.workspace_id}, in_flight={self.messages_in_flight})>"


# ─────────────────────────────────────────────────────────────────────────────
# Event Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def create_event_id() -> str:
    """Generate unique event ID."""
    import uuid
    return str(uuid.uuid4())


def get_aggregation_key(
    event_type: str,
    workspace_id: int,
    labels: dict | None = None,
    category: str | None = None,
) -> str:
    """
    Generate aggregation key for rollup grouping.

    Args:
        event_type: Event type (e.g., "message.sent")
        workspace_id: Workspace ID
        labels: Optional dimension labels
        category: Optional event category

    Returns:
        Aggregation key string
    """
    parts = [event_type, f"ws={workspace_id}"]

    if category:
        parts.append(f"cat={category}")

    if labels:
        for key, value in sorted(labels.items()):
            parts.append(f"{key}={value}")

    return ":".join(parts)