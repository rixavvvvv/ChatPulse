"""
Analytics aggregation workers.

Provides:
- Hourly rollups
- Daily rollups
- Campaign aggregation
- Workspace aggregation
- Retention management
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import and_, func, select, text
from sqlalchemy.dialects.postgresql import insert

from app.core.config import get_settings
from app.db import get_db_session
from app.models.analytics import (
    AnalyticsEvent,
    AnalyticsRollup,
    CampaignMetrics,
    RealtimeMetrics,
    RollupGranularity,
    WorkspaceMetrics,
    get_aggregation_key,
)

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Base Aggregation Worker
# ─────────────────────────────────────────────────────────────────────────────

class AggregationWorker:
    """Base class for aggregation workers."""

    def __init__(self, granularity: RollupGranularity):
        self._granularity = granularity
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self) -> None:
        """Start the aggregation worker."""
        if self._running:
            return

        self._running = True
        interval = self._get_interval()
        self._task = asyncio.create_task(self._run_loop(interval))
        logger.info(f"Started {self._granularity.value} aggregation worker")

    async def stop(self) -> None:
        """Stop the aggregation worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info(f"Stopped {self._granularity.value} aggregation worker")

    def _get_interval(self) -> int:
        """Get run interval in seconds."""
        intervals = {
            RollupGranularity.MINUTE_1: 60,
            RollupGranularity.MINUTE_5: 300,
            RollupGranularity.MINUTE_15: 900,
            RollupGranularity.HOUR_1: 3600,
            RollupGranularity.DAY_1: 86400,
            RollupGranularity.WEEK_1: 604800,
        }
        return intervals.get(self._granularity, 300)

    async def _run_loop(self, interval: int) -> None:
        """Run aggregation loop."""
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break

                start = datetime.now(timezone.utc)
                await self._aggregate()
                duration = (datetime.now(timezone.utc) - start).total_seconds()

                logger.debug(f"{self._granularity.value} aggregation completed in {duration:.2f}s")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in {self._granularity.value} aggregation: {exc}")

    async def _aggregate(self) -> int:
        """Perform aggregation. Override in subclasses."""
        raise NotImplementedError


# ─────────────────────────────────────────────────────────────────────────────
# Event Rollup Aggregation
# ─────────────────────────────────────────────────────────────────────────────

class EventRollupWorker(AggregationWorker):
    """Aggregates events into rollups."""

    def __init__(self, granularity: RollupGranularity):
        super().__init__(granularity)

    async def _aggregate(self) -> int:
        """Aggregate events into rollups."""
        async with get_db_session() as session:
            # Calculate window
            now = datetime.now(timezone.utc)
            window = self._get_window_size()
            window_start = now.replace(second=0, microsecond=0) - window
            window_end = window_start + window

            # Get unprocessed events grouped by aggregation key
            query = text("""
                SELECT
                    workspace_id,
                    event_type,
                    event_category,
                    labels,
                    aggregation_key,
                    COUNT(*) as total_count,
                    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failure_count,
                    SUM(COALESCE(value_numeric, 0)) as value_sum,
                    AVG(COALESCE(value_numeric, 0)) as value_avg,
                    MIN(value_numeric) as value_min,
                    MAX(value_numeric) as value_max,
                    SUM(COALESCE(duration_ms, 0)) as duration_sum,
                    AVG(COALESCE(duration_ms, 0)) as duration_avg,
                    MIN(duration_ms) as duration_min,
                    MAX(duration_ms) as duration_max,
                    COUNT(DISTINCT contact_id) as unique_contacts,
                    COUNT(DISTINCT campaign_id) as unique_campaigns,
                    COUNT(DISTINCT user_id) as unique_users
                FROM analytics_events
                WHERE processed = false
                    AND occurred_at >= :window_start
                    AND occurred_at < :window_end
                GROUP BY workspace_id, event_type, event_category, labels, aggregation_key
            """)

            result = await session.execute(query, {
                "window_start": window_start,
                "window_end": window_end,
            })
            rows = result.fetchall()

            count = 0
            for row in rows:
                rollup = AnalyticsRollup(
                    workspace_id=row.workspace_id,
                    rollup_key=row.aggregation_key,
                    granularity=self._granularity.value,
                    window_start=window_start,
                    window_end=window_end,
                    event_type=row.event_type,
                    event_category=row.event_category,
                    total_count=row.total_count,
                    success_count=row.success_count or 0,
                    failure_count=row.failure_count or 0,
                    value_sum=row.value_sum or 0,
                    value_avg=row.value_avg,
                    value_min=row.value_min,
                    value_max=row.value_max,
                    duration_sum=row.duration_sum or 0,
                    duration_avg=row.duration_avg,
                    duration_min=row.duration_min,
                    duration_max=row.duration_max,
                    unique_contacts=row.unique_contacts,
                    unique_campaigns=row.unique_campaigns,
                    unique_users=row.unique_users,
                    labels=row.labels,
                )
                session.add(rollup)
                count += 1

            # Mark events as processed
            update_query = text("""
                UPDATE analytics_events
                SET processed = true, processed_at = :now
                WHERE processed = false
                    AND occurred_at >= :window_start
                    AND occurred_at < :window_end
            """)
            await session.execute(update_query, {
                "window_start": window_start,
                "window_end": window_end,
                "now": now,
            })

            await session.commit()
            return count

    def _get_window_size(self) -> timedelta:
        """Get window size for granularity."""
        windows = {
            RollupGranularity.MINUTE_1: timedelta(minutes=1),
            RollupGranularity.MINUTE_5: timedelta(minutes=5),
            RollupGranularity.MINUTE_15: timedelta(minutes=15),
            RollupGranularity.HOUR_1: timedelta(hours=1),
            RollupGranularity.DAY_1: timedelta(days=1),
            RollupGranularity.WEEK_1: timedelta(weeks=1),
        }
        return windows.get(self._granularity, timedelta(hours=1))


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Aggregation Worker
# ─────────────────────────────────────────────────────────────────────────────

class WorkspaceAggregationWorker(AggregationWorker):
    """Aggregates workspace-level metrics."""

    async def _aggregate(self) -> int:
        """Aggregate workspace metrics."""
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            period_end = period_start + timedelta(days=1)

            # Aggregate message metrics
            message_query = text("""
                INSERT INTO workspace_metrics (
                    workspace_id, period_start, period_end,
                    messages_sent, messages_delivered, messages_failed,
                    campaigns_created, campaigns_completed, campaigns_failed,
                    webhooks_received, webhooks_processed, webhooks_failed,
                    recoveries_detected, recoveries_completed, recoveries_failed,
                    created_at, updated_at
                )
                SELECT
                    workspace_id,
                    :period_start,
                    :period_end,
                    SUM(CASE WHEN event_type = 'message.sent' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'message.delivered' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'message.failed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'campaign.created' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'campaign.completed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'campaign.failed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'webhook.received' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'webhook.processed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'webhook.failed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'recovery.detected' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'recovery.completed' THEN 1 ELSE 0 END),
                    SUM(CASE WHEN event_type = 'recovery.failed' THEN 1 ELSE 0 END),
                    :now,
                    :now
                FROM analytics_events
                WHERE occurred_at >= :period_start AND occurred_at < :period_end
                GROUP BY workspace_id
                ON CONFLICT (workspace_id) DO UPDATE SET
                    messages_sent = EXCLUDED.messages_sent,
                    messages_delivered = EXCLUDED.messages_delivered,
                    messages_failed = EXCLUDED.messages_failed,
                    campaigns_created = EXCLUDED.campaigns_created,
                    campaigns_completed = EXCLUDED.campaigns_completed,
                    campaigns_failed = EXCLUDED.campaigns_failed,
                    webhooks_received = EXCLUDED.webhooks_received,
                    webhooks_processed = EXCLUDED.webhooks_processed,
                    webhooks_failed = EXCLUDED.webhooks_failed,
                    recoveries_detected = EXCLUDED.recoveries_detected,
                    recoveries_completed = EXCLUDED.recoveries_completed,
                    recoveries_failed = EXCLUDED.recoveries_failed,
                    updated_at = EXCLUDED.updated_at
            """)

            await session.execute(message_query, {
                "period_start": period_start,
                "period_end": period_end,
                "now": now,
            })
            await session.commit()

            return 1


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Aggregation Worker
# ─────────────────────────────────────────────────────────────────────────────

class CampaignAggregationWorker(AggregationWorker):
    """Aggregates campaign-level metrics."""

    def __init__(self):
        super().__init__(RollupGranularity.HOUR_1)

    async def _aggregate(self) -> int:
        """Aggregate campaign metrics."""
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=1)
            window_end = now

            # Get campaign event aggregates
            query = text("""
                WITH campaign_stats AS (
                    SELECT
                        campaign_id,
                        workspace_id,
                        COUNT(*) FILTER (WHERE event_type = 'message.sent') as sent_count,
                        COUNT(*) FILTER (WHERE event_type = 'message.delivered') as delivered_count,
                        COUNT(*) FILTER (WHERE event_type = 'message.read') as read_count,
                        COUNT(*) FILTER (WHERE event_type = 'message.failed') as failed_count,
                        AVG(duration_ms) FILTER (WHERE event_type = 'message.sent') as avg_duration_ms,
                        MIN(duration_ms) FILTER (WHERE event_type = 'message.sent') as min_duration_ms,
                        MAX(duration_ms) FILTER (WHERE event_type = 'message.sent') as max_duration_ms,
                        COUNT(*) FILTER (WHERE event_type = 'recovery.started') as recovery_count,
                        COUNT(*) FILTER (WHERE event_type = 'recovery.completed') as recovery_success_count
                    FROM analytics_events
                    WHERE campaign_id IS NOT NULL
                        AND occurred_at >= :window_start
                        AND occurred_at < :window_end
                    GROUP BY campaign_id, workspace_id
                )
                INSERT INTO campaign_metrics (
                    campaign_id, workspace_id,
                    sent_count, delivered_count, read_count, failed_count,
                    avg_per_recipient_ms, min_recipient_ms, max_recipient_ms,
                    recovery_count, recovery_success_count,
                    updated_at
                )
                SELECT
                    campaign_id,
                    workspace_id,
                    COALESCE(sent_count, 0),
                    COALESCE(delivered_count, 0),
                    COALESCE(read_count, 0),
                    COALESCE(failed_count, 0),
                    avg_duration_ms,
                    min_duration_ms,
                    max_duration_ms,
                    COALESCE(recovery_count, 0),
                    COALESCE(recovery_success_count, 0),
                    :now
                FROM campaign_stats
                ON CONFLICT (campaign_id) DO UPDATE SET
                    sent_count = campaign_metrics.sent_count + EXCLUDED.sent_count,
                    delivered_count = campaign_metrics.delivered_count + EXCLUDED.delivered_count,
                    read_count = campaign_metrics.read_count + EXCLUDED.read_count,
                    failed_count = campaign_metrics.failed_count + EXCLUDED.failed_count,
                    avg_per_recipient_ms = COALESCE(EXCLUDED.avg_per_recipient_ms, campaign_metrics.avg_per_recipient_ms),
                    min_recipient_ms = LEAST(COALESCE(campaign_metrics.min_recipient_ms, 999999), COALESCE(EXCLUDED.min_recipient_ms, 999999)),
                    max_recipient_ms = GREATEST(COALESCE(campaign_metrics.max_recipient_ms, 0), COALESCE(EXCLUDED.max_recipient_ms, 0)),
                    recovery_count = campaign_metrics.recovery_count + EXCLUDED.recovery_count,
                    recovery_success_count = campaign_metrics.recovery_success_count + EXCLUDED.recovery_success_count,
                    updated_at = EXCLUDED.updated_at
            """)

            await session.execute(query, {
                "window_start": window_start,
                "window_end": window_end,
                "now": now,
            })
            await session.commit()

            return 1


# ─────────────────────────────────────────────────────────────────────────────
# Percentile Calculation Worker
# ─────────────────────────────────────────────────────────────────────────────

class PercentileAggregationWorker(AggregationWorker):
    """Calculates percentiles for duration metrics."""

    def __init__(self):
        super().__init__(RollupGranularity.HOUR_1)

    async def _aggregate(self) -> int:
        """Calculate percentiles for rollups."""
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=2)
            window_end = now - timedelta(hours=1)

            # Calculate percentiles using window functions
            query = text("""
                WITH duration_data AS (
                    SELECT
                        workspace_id,
                        event_type,
                        labels,
                        duration_ms
                    FROM analytics_events
                    WHERE event_type LIKE '%.duration' OR event_type LIKE '%.latency'
                        AND occurred_at >= :window_start
                        AND occurred_at < :window_end
                        AND duration_ms IS NOT NULL
                ),
                percentiles AS (
                    SELECT
                        workspace_id,
                        event_type,
                        labels,
                        PERCENTILE_CONT(0.50) WITHIN GROUP (ORDER BY duration_ms) as p50,
                        PERCENTILE_CONT(0.95) WITHIN GROUP (ORDER BY duration_ms) as p95,
                        PERCENTILE_CONT(0.99) WITHIN GROUP (ORDER BY duration_ms) as p99
                    FROM duration_data
                    GROUP BY workspace_id, event_type, labels
                )
                UPDATE analytics_rollups ar
                SET
                    duration_p50 = p.p50,
                    duration_p95 = p.p95,
                    duration_p99 = p.p99,
                    updated_at = :now
                FROM percentiles p
                WHERE ar.workspace_id = p.workspace_id
                    AND ar.event_type = p.event_type
                    AND ar.labels = p.labels
                    AND ar.window_start >= :window_start
                    AND ar.window_start < :window_end
            """)

            await session.execute(query, {
                "window_start": window_start,
                "window_end": window_end,
                "now": now,
            })
            await session.commit()

            return 1


# ─────────────────────────────────────────────────────────────────────────────
# Retention Worker
# ─────────────────────────────────────────────────────────────────────────────

class RetentionWorker:
    """Manages analytics data retention."""

    def __init__(self):
        self._running = False
        self._task: asyncio.Task | None = None

    async def start(self, interval_hours: int = 24) -> None:
        """Start retention worker."""
        if self._running:
            return

        self._running = True
        self._task = asyncio.create_task(self._run_loop(interval_hours * 3600))
        logger.info("Started retention worker")

    async def stop(self) -> None:
        """Stop retention worker."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Stopped retention worker")

    async def _run_loop(self, interval: int) -> None:
        """Run retention loop."""
        while self._running:
            try:
                await asyncio.sleep(interval)
                if not self._running:
                    break

                await self._apply_retention()
                logger.info("Retention cleanup completed")

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in retention worker: {exc}")

    async def _apply_retention(self) -> None:
        """Apply retention policies."""
        async with get_db_session() as session:
            now = datetime.now(timezone.utc)

            # Raw events retention: 90 days
            cutoff_raw = now - timedelta(days=90)
            raw_delete = text("""
                DELETE FROM analytics_events
                WHERE occurred_at < :cutoff
                    AND processed = true
            """)
            result = await session.execute(raw_delete, {"cutoff": cutoff_raw})
            logger.info(f"Deleted {result.rowcount} raw events older than 90 days")

            # 1m rollups retention: 7 days
            cutoff_1m = now - timedelta(days=7)
            rollup_delete = text("""
                DELETE FROM analytics_rollups
                WHERE granularity = '1m'
                    AND window_end < :cutoff
            """)
            result = await session.execute(rollup_delete, {"cutoff": cutoff_1m})
            logger.info(f"Deleted {result.rowcount} 1m rollups older than 7 days")

            # 5m rollups retention: 30 days
            cutoff_5m = now - timedelta(days=30)
            rollup_delete = text("""
                DELETE FROM analytics_rollups
                WHERE granularity = '5m'
                    AND window_end < :cutoff
            """)
            result = await session.execute(rollup_delete, {"cutoff": cutoff_5m})
            logger.info(f"Deleted {result.rowcount} 5m rollups older than 30 days")

            # 1h rollups retention: 90 days
            cutoff_1h = now - timedelta(days=90)
            rollup_delete = text("""
                DELETE FROM analytics_rollups
                WHERE granularity = '1h'
                    AND window_end < :cutoff
            """)
            result = await session.execute(rollup_delete, {"cutoff": cutoff_1h})
            logger.info(f"Deleted {result.rowcount} 1h rollups older than 90 days")

            # 1d rollups retention: 365 days
            cutoff_1d = now - timedelta(days=365)
            rollup_delete = text("""
                DELETE FROM analytics_rollups
                WHERE granularity = '1d'
                    AND window_end < :cutoff
            """)
            result = await session.execute(rollup_delete, {"cutoff": cutoff_1d})
            logger.info(f"Deleted {result.rowcount} 1d rollups older than 365 days")

            await session.commit()


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation Manager
# ─────────────────────────────────────────────────────────────────────────────

class AggregationManager:
    """Manages all aggregation workers."""

    def __init__(self):
        self._workers: list[AggregationWorker] = []
        self._retention: RetentionWorker | None = None

    async def start_all(self) -> None:
        """Start all aggregation workers."""
        # Event rollup workers
        self._workers.append(EventRollupWorker(RollupGranularity.MINUTE_1))
        self._workers.append(EventRollupWorker(RollupGranularity.MINUTE_5))
        self._workers.append(EventRollupWorker(RollupGranularity.HOUR_1))
        self._workers.append(EventRollupWorker(RollupGranularity.DAY_1))

        # Special purpose workers
        self._workers.append(WorkspaceAggregationWorker(RollupGranularity.DAY_1))
        self._workers.append(CampaignAggregationWorker())
        self._workers.append(PercentileAggregationWorker())

        # Retention worker
        self._retention = RetentionWorker()

        for worker in self._workers:
            await worker.start()

        await self._retention.start()

        logger.info(f"Started {len(self._workers)} aggregation workers")

    async def stop_all(self) -> None:
        """Stop all aggregation workers."""
        for worker in self._workers:
            await worker.stop()

        if self._retention:
            await self._retention.stop()

        self._workers.clear()
        logger.info("Stopped all aggregation workers")


# Global aggregation manager
_aggregation_manager: AggregationManager | None = None


def get_aggregation_manager() -> AggregationManager:
    """Get or create the global aggregation manager."""
    global _aggregation_manager
    if _aggregation_manager is None:
        _aggregation_manager = AggregationManager()
    return _aggregation_manager