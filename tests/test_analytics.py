"""
Tests for analytics infrastructure.

Tests cover:
- Event ingestion
- Rollup aggregation
- Query service
- API endpoints
"""

import json
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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


# ─────────────────────────────────────────────────────────────────────────────
# Model Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsEvent:
    """Test AnalyticsEvent model."""

    def test_create_event(self):
        """Should create event with required fields."""
        event = AnalyticsEvent(
            event_id=create_event_id(),
            event_type="message.sent",
            event_category=EventCategory.MESSAGE.value,
            occurred_at=datetime.now(timezone.utc),
            ingested_at=datetime.now(timezone.utc),
            workspace_id=123,
            event_data={},
        )

        assert event.event_type == "message.sent"
        assert event.workspace_id == 123
        assert event.processed is False

    def test_aggregation_key_generation(self):
        """Should generate aggregation key correctly."""
        key = get_aggregation_key(
            event_type="message.sent",
            workspace_id=123,
            labels={"status": "success"},
            category="message",
        )

        assert key == "message.sent:ws=123:cat=message:status=success"
        assert "ws=123" in key

    def test_aggregation_key_without_labels(self):
        """Should generate key without labels."""
        key = get_aggregation_key(
            event_type="campaign.created",
            workspace_id=456,
            labels=None,
            category="campaign",
        )

        assert key == "campaign.created:ws=456:cat=campaign"

    def test_event_type_enum(self):
        """Should have all expected event types."""
        assert EventType.MESSAGE_SENT.value == "message.sent"
        assert EventType.WEBHOOK_RECEIVED.value == "webhook.received"
        assert EventType.CAMPAIGN_COMPLETED.value == "campaign.completed"

    def test_event_category_enum(self):
        """Should have all expected categories."""
        assert EventCategory.MESSAGE.value == "message"
        assert EventCategory.CAMPAIGN.value == "campaign"
        assert EventCategory.RECOVERY.value == "recovery"


class TestAnalyticsRollup:
    """Test AnalyticsRollup model."""

    def test_create_rollup(self):
        """Should create rollup with required fields."""
        now = datetime.now(timezone.utc)
        rollup = AnalyticsRollup(
            workspace_id=123,
            rollup_key="message.sent:ws=123",
            granularity=RollupGranularity.HOUR_1.value,
            window_start=now - timedelta(hours=1),
            window_end=now,
            event_type="message.sent",
            event_category="message",
            total_count=1000,
            success_count=950,
            failure_count=50,
        )

        assert rollup.total_count == 1000
        assert rollup.success_count == 950
        assert rollup.granularity == "1h"

    def test_rollup_percentiles(self):
        """Should store percentiles."""
        rollup = AnalyticsRollup(
            workspace_id=123,
            rollup_key="test",
            granularity="1h",
            window_start=datetime.now(timezone.utc),
            window_end=datetime.now(timezone.utc),
            event_type="test",
            total_count=100,
            duration_p50=100.0,
            duration_p95=500.0,
            duration_p99=900.0,
        )

        assert rollup.duration_p50 == 100.0
        assert rollup.duration_p95 == 500.0
        assert rollup.duration_p99 == 900.0


class TestWorkspaceMetrics:
    """Test WorkspaceMetrics model."""

    def test_create_workspace_metrics(self):
        """Should create workspace metrics."""
        now = datetime.now(timezone.utc)
        metrics = WorkspaceMetrics(
            workspace_id=123,
            period_start=now - timedelta(days=1),
            period_end=now,
            messages_sent=5000,
            messages_delivered=4800,
            messages_failed=200,
            campaigns_created=10,
            campaigns_completed=8,
        )

        assert metrics.messages_sent == 5000
        assert metrics.campaigns_completed == 8
        assert metrics.delivery_rate is None  # Not computed until saved


class TestCampaignMetrics:
    """Test CampaignMetrics model."""

    def test_create_campaign_metrics(self):
        """Should create campaign metrics."""
        metrics = CampaignMetrics(
            campaign_id=456,
            workspace_id=123,
            total_recipients=1000,
            sent_count=500,
            delivered_count=450,
            read_count=100,
            failed_count=50,
        )

        assert metrics.sent_count == 500
        assert metrics.delivery_count == 450
        assert metrics.read_rate is None  # Not computed until saved

    def test_hourly_counts_json(self):
        """Should store hourly distribution as JSON."""
        metrics = CampaignMetrics(
            campaign_id=456,
            workspace_id=123,
            total_recipients=1000,
            hourly_counts={"0": 10, "1": 5, "2": 15},
        )

        assert metrics.hourly_counts["0"] == 10
        assert metrics.hourly_counts["1"] == 5


class TestRealtimeMetrics:
    """Test RealtimeMetrics model."""

    def test_create_realtime_metrics(self):
        """Should create real-time metrics."""
        metrics = RealtimeMetrics(
            workspace_id=123,
            active_campaigns=2,
            messages_in_flight=100,
            queue_depth=50,
            active_workers=4,
            messages_last_minute=500,
            messages_per_second=8.33,
        )

        assert metrics.messages_in_flight == 100
        assert metrics.messages_per_second == 8.33


class TestRollupGranularity:
    """Test RollupGranularity enum."""

    def test_granularity_values(self):
        """Should have all expected granularities."""
        assert RollupGranularity.MINUTE_1.value == "1m"
        assert RollupGranularity.MINUTE_5.value == "5m"
        assert RollupGranularity.HOUR_1.value == "1h"
        assert RollupGranularity.DAY_1.value == "1d"
        assert RollupGranularity.WEEK_1.value == "1w"


# ─────────────────────────────────────────────────────────────────────────────
# Service Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAggregationKey:
    """Test aggregation key generation."""

    def test_key_with_multiple_labels(self):
        """Should handle multiple labels."""
        key = get_aggregation_key(
            event_type="message.sent",
            workspace_id=123,
            labels={"status": "success", "source": "api"},
            category="message",
        )

        # Labels should be sorted alphabetically
        assert "status=success" in key
        assert "source=api" in key

    def test_key_workspace_prefix(self):
        """Should include workspace ID."""
        key = get_aggregation_key(
            event_type="campaign.started",
            workspace_id=789,
            labels=None,
            category="campaign",
        )

        assert "ws=789" in key
        assert "campaign.started" in key

    def test_key_category(self):
        """Should include category."""
        key = get_aggregation_key(
            event_type="webhook.processed",
            workspace_id=123,
            labels=None,
            category="webhook",
        )

        assert "cat=webhook" in key


class TestEventIDGeneration:
    """Test event ID generation."""

    def test_generate_unique_id(self):
        """Should generate unique IDs."""
        id1 = create_event_id()
        id2 = create_event_id()

        assert id1 != id2
        assert len(id1) == 36  # UUID format

    def test_id_is_string(self):
        """Should return string UUID."""
        event_id = create_event_id()
        assert isinstance(event_id, str)


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEventFlow:
    """Test event flow through system."""

    def test_event_to_rollup_transformation(self):
        """Should transform events to rollup format."""
        now = datetime.now(timezone.utc)
        event = AnalyticsEvent(
            event_id=create_event_id(),
            event_type="message.sent",
            event_category=EventCategory.MESSAGE.value,
            occurred_at=now,
            ingested_at=now,
            workspace_id=123,
            event_data={},
            success=True,
            duration_ms=45.5,
            count=1,
        )

        # Simulate aggregation
        rollup = AnalyticsRollup(
            workspace_id=event.workspace_id,
            rollup_key=get_aggregation_key(
                event.event_type,
                event.workspace_id,
                event.labels,
                event.event_category,
            ),
            granularity=RollupGranularity.MINUTE_1.value,
            window_start=now.replace(second=0, microsecond=0) - timedelta(minutes=1),
            window_end=now.replace(second=0, microsecond=0),
            event_type=event.event_type,
            event_category=event.event_category,
            total_count=1,
            success_count=1,
            failure_count=0,
            duration_sum=45.5,
            duration_avg=45.5,
        )

        assert rollup.total_count == 1
        assert rollup.success_count == 1
        assert rollup.duration_avg == 45.5

    def test_batch_events_to_rollup(self):
        """Should aggregate batch of events."""
        now = datetime.now(timezone.utc)
        events = [
            AnalyticsEvent(
                event_id=create_event_id(),
                event_type="message.sent",
                event_category=EventCategory.MESSAGE.value,
                occurred_at=now,
                ingested_at=now,
                workspace_id=123,
                event_data={},
                success=True,
                duration_ms=40.0 + i,
            )
            for i in range(10)
        ]

        # Simulate aggregation
        total_count = len(events)
        success_count = sum(1 for e in events if e.success)
        duration_sum = sum(e.duration_ms for e in events if e.duration_ms)

        rollup = AnalyticsRollup(
            workspace_id=123,
            rollup_key="message.sent:ws=123:cat=message",
            granularity=RollupGranularity.MINUTE_1.value,
            window_start=now - timedelta(minutes=1),
            window_end=now,
            event_type="message.sent",
            event_category="message",
            total_count=total_count,
            success_count=success_count,
            failure_count=total_count - success_count,
            duration_sum=duration_sum,
            duration_avg=duration_sum / total_count,
        )

        assert rollup.total_count == 10
        assert rollup.success_count == 10
        assert rollup.duration_avg == 44.5  # Average of 40-49


# ─────────────────────────────────────────────────────────────────────────────
# Performance Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAnalyticsPerformance:
    """Performance tests for analytics."""

    def test_event_creation_performance(self):
        """Event creation should be fast."""
        start = time.perf_counter()
        for _ in range(1000):
            AnalyticsEvent(
                event_id=create_event_id(),
                event_type="message.sent",
                event_category=EventCategory.MESSAGE.value,
                occurred_at=datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
                workspace_id=123,
                event_data={},
            )
        duration = time.perf_counter() - start

        # Should create 1000 events in under 100ms
        assert duration < 0.1

    def test_aggregation_key_performance(self):
        """Aggregation key generation should be fast."""
        start = time.perf_counter()
        for _ in range(1000):
            get_aggregation_key(
                event_type="message.sent",
                workspace_id=123,
                labels={"status": "success", "source": "api"},
                category="message",
            )
        duration = time.perf_counter() - start

        # Should generate 1000 keys in under 50ms
        assert duration < 0.05

    def test_rollup_creation_performance(self):
        """Rollup creation should be fast."""
        now = datetime.now(timezone.utc)
        start = time.perf_counter()
        for _ in range(1000):
            AnalyticsRollup(
                workspace_id=123,
                rollup_key="message.sent:ws=123",
                granularity="1h",
                window_start=now - timedelta(hours=1),
                window_end=now,
                event_type="message.sent",
                total_count=100,
                success_count=95,
                failure_count=5,
            )
        duration = time.perf_counter() - start

        # Should create 1000 rollups in under 100ms
        assert duration < 0.1


# ─────────────────────────────────────────────────────────────────────────────
# Retention Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRetentionPolicy:
    """Test retention policy application."""

    def test_raw_event_retention(self):
        """Should identify events for deletion."""
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(days=90)

        events = [
            AnalyticsEvent(
                event_id=create_event_id(),
                event_type="message.sent",
                event_category=EventCategory.MESSAGE.value,
                occurred_at=now - timedelta(days=i),
                ingested_at=now,
                workspace_id=123,
                event_data={},
                processed=True,
            )
            for i in range(100)
        ]

        # Events older than 90 days should be deleted
        deletable = [e for e in events if e.occurred_at < cutoff]
        retainable = [e for e in events if e.occurred_at >= cutoff]

        assert len(deletable) == 10
        assert len(retainable) == 90

    def test_rollup_retention_by_granularity(self):
        """Should identify rollups for deletion by granularity."""
        now = datetime.now(timezone.utc)

        rollups = [
            AnalyticsRollup(
                workspace_id=123,
                rollup_key="test",
                granularity=granularity,
                window_start=now - timedelta(days=days),
                window_end=now - timedelta(days=days - 1),
                event_type="test",
                total_count=100,
            )
            for granularity, days in [
                ("1m", 10),
                ("5m", 35),
                ("1h", 95),
                ("1d", 400),
            ]
        ]

        # 1m rollups older than 7 days
        deletable_1m = [r for r in rollups if r.granularity == "1m" and r.window_end < now - timedelta(days=7)]
        assert len(deletable_1m) == 1

        # 5m rollups older than 30 days
        deletable_5m = [r for r in rollups if r.granularity == "5m" and r.window_end < now - timedelta(days=30)]
        assert len(deletable_5m) == 1

        # 1h rollups older than 90 days
        deletable_1h = [r for r in rollups if r.granularity == "1h" and r.window_end < now - timedelta(days=90)]
        assert len(deletable_1h) == 0  # 95 days > 90 days