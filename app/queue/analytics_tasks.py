"""
Analytics tasks for Celery queue.

Provides:
- Event ingestion tasks
- Rollup aggregation tasks
- Cleanup tasks
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from celery import shared_task

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

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Event Ingestion Tasks
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name="analytics.ingest_event")
def ingest_analytics_event(self, event_data: dict[str, Any]) -> dict[str, Any]:
    """
    Celery task to ingest a single analytics event.

    Args:
        event_data: Event dictionary containing:
            - event_type: str
            - workspace_id: int
            - occurred_at: str (ISO format, optional)
            - campaign_id: int (optional)
            - contact_id: int (optional)
            - duration_ms: float (optional)
            - success: bool (optional)
            - error_type: str (optional)
            - trace_id: str (optional)
            - labels: dict (optional)

    Returns:
        dict with event_id and status
    """
    async def _run():
        from app.services.analytics_service import AnalyticsIngestionService

        event_type = event_data.get("event_type")
        workspace_id = event_data["workspace_id"]

        # Determine category
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

        category = "unknown"
        for prefix, cat in category_map.items():
            if event_type.startswith(prefix):
                category = cat
                break

        occurred_at = None
        if event_data.get("occurred_at"):
            occurred_at = datetime.fromisoformat(event_data["occurred_at"])

        async with get_db_session() as session:
            event = AnalyticsEvent(
                event_id=create_event_id(),
                event_type=event_type,
                event_category=category,
                occurred_at=occurred_at or datetime.now(timezone.utc),
                ingested_at=datetime.now(timezone.utc),
                workspace_id=workspace_id,
                campaign_id=event_data.get("campaign_id"),
                user_id=event_data.get("user_id"),
                contact_id=event_data.get("contact_id"),
                queue_name=event_data.get("queue_name"),
                task_id=event_data.get("task_id"),
                worker_id=event_data.get("worker_id"),
                event_data=event_data.get("event_data", {}),
                value_numeric=event_data.get("value_numeric"),
                duration_ms=event_data.get("duration_ms"),
                count=event_data.get("count"),
                source=event_data.get("source"),
                trace_id=event_data.get("trace_id"),
                request_id=event_data.get("request_id"),
                success=event_data.get("success"),
                error_type=event_data.get("error_type"),
                labels=event_data.get("labels"),
                processed=False,
                aggregation_key=get_aggregation_key(
                    event_type, workspace_id, event_data.get("labels"), category
                ),
            )
            session.add(event)
            await session.commit()
            await session.refresh(event)

            return {"event_id": str(event.event_id), "status": "ingested"}

    return asyncio.run(_run())


@shared_task(bind=True, name="analytics.ingest_batch")
def ingest_analytics_batch(self, events: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Celery task to ingest multiple analytics events.

    Args:
        events: List of event dictionaries

    Returns:
        dict with count and status
    """
    async def _run():
        from sqlalchemy import text

        async with get_db_session() as session:
            # Use bulk insert
            now = datetime.now(timezone.utc)

            for event_data in events:
                event_type = event_data.get("event_type")
                workspace_id = event_data["workspace_id"]

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

                category = "unknown"
                for prefix, cat in category_map.items():
                    if event_type.startswith(prefix):
                        category = cat
                        break

                occurred_at = None
                if event_data.get("occurred_at"):
                    occurred_at = datetime.fromisoformat(event_data["occurred_at"])

                event = AnalyticsEvent(
                    event_id=create_event_id(),
                    event_type=event_type,
                    event_category=category,
                    occurred_at=occurred_at or now,
                    ingested_at=now,
                    workspace_id=workspace_id,
                    campaign_id=event_data.get("campaign_id"),
                    user_id=event_data.get("user_id"),
                    contact_id=event_data.get("contact_id"),
                    queue_name=event_data.get("queue_name"),
                    task_id=event_data.get("task_id"),
                    worker_id=event_data.get("worker_id"),
                    event_data=event_data.get("event_data", {}),
                    value_numeric=event_data.get("value_numeric"),
                    duration_ms=event_data.get("duration_ms"),
                    count=event_data.get("count"),
                    source=event_data.get("source"),
                    trace_id=event_data.get("trace_id"),
                    request_id=event_data.get("request_id"),
                    success=event_data.get("success"),
                    error_type=event_data.get("error_type"),
                    labels=event_data.get("labels"),
                    processed=False,
                    aggregation_key=get_aggregation_key(
                        event_type, workspace_id, event_data.get("labels"), category
                    ),
                )
                session.add(event)

            await session.commit()
            return {"count": len(events), "status": "ingested"}

    return asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation Tasks
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name="analytics.aggregate_rollups")
def aggregate_rollups_task(self, granularity: str = "1h") -> dict[str, Any]:
    """
    Celery task to aggregate events into rollups.

    Args:
        granularity: Rollup granularity (1m, 5m, 1h, 1d)

    Returns:
        dict with count and status
    """
    async def _run():
        from sqlalchemy import text

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)

            # Calculate window based on granularity
            window_map = {
                "1m": timedelta(minutes=1),
                "5m": timedelta(minutes=5),
                "15m": timedelta(minutes=15),
                "1h": timedelta(hours=1),
                "1d": timedelta(days=1),
            }
            window = window_map.get(granularity, timedelta(hours=1))

            window_start = now.replace(second=0, microsecond=0) - window
            window_end = window_start + window

            # Aggregate events
            query = text("""
                INSERT INTO analytics_rollups (
                    workspace_id, rollup_key, granularity,
                    window_start, window_end,
                    event_type, event_category,
                    total_count, success_count, failure_count,
                    value_sum, value_avg, value_min, value_max,
                    duration_sum, duration_avg, duration_min, duration_max,
                    unique_contacts, unique_campaigns, unique_users,
                    labels, created_at, updated_at
                )
                SELECT
                    workspace_id,
                    aggregation_key,
                    :granularity,
                    :window_start,
                    :window_end,
                    event_type,
                    event_category,
                    COUNT(*) as total_count,
                    SUM(CASE WHEN success = true THEN 1 ELSE 0 END) as success_count,
                    SUM(CASE WHEN success = false THEN 1 ELSE 0 END) as failure_count,
                    COALESCE(SUM(value_numeric), 0) as value_sum,
                    COALESCE(AVG(value_numeric), 0) as value_avg,
                    MIN(value_numeric) as value_min,
                    MAX(value_numeric) as value_max,
                    COALESCE(SUM(duration_ms), 0) as duration_sum,
                    COALESCE(AVG(duration_ms), 0) as duration_avg,
                    MIN(duration_ms) as duration_min,
                    MAX(duration_ms) as duration_max,
                    COUNT(DISTINCT contact_id) as unique_contacts,
                    COUNT(DISTINCT campaign_id) as unique_campaigns,
                    COUNT(DISTINCT user_id) as unique_users,
                    labels,
                    :now,
                    :now
                FROM analytics_events
                WHERE processed = false
                    AND occurred_at >= :window_start
                    AND occurred_at < :window_end
                GROUP BY workspace_id, event_type, event_category, labels, aggregation_key
                ON CONFLICT DO NOTHING
            """)

            result = await session.execute(query, {
                "granularity": granularity,
                "window_start": window_start,
                "window_end": window_end,
                "now": now,
            })

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
            return {
                "granularity": granularity,
                "count": result.rowcount,
                "status": "aggregated"
            }

    return asyncio.run(_run())


@shared_task(bind=True, name="analytics.aggregate_workspace")
def aggregate_workspace_metrics_task(self) -> dict[str, Any]:
    """
    Celery task to aggregate workspace-level metrics.

    Returns:
        dict with status
    """
    async def _run():
        from sqlalchemy import text

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            period_end = period_start + timedelta(days=1)

            query = text("""
                INSERT INTO workspace_metrics (
                    workspace_id, period_start, period_end,
                    messages_sent, messages_delivered, messages_failed,
                    campaigns_created, campaigns_completed, campaigns_failed,
                    webhooks_received, webhooks_processed, webhooks_failed,
                    recoveries_detected, recoveries_completed, recoveries_failed,
                    rate_limit_allowed, rate_limit_rejected,
                    created_at, updated_at
                )
                SELECT
                    workspace_id,
                    :period_start,
                    :period_end,
                    COUNT(*) FILTER (WHERE event_type = 'message.sent') as messages_sent,
                    COUNT(*) FILTER (WHERE event_type = 'message.delivered') as messages_delivered,
                    COUNT(*) FILTER (WHERE event_type = 'message.failed') as messages_failed,
                    COUNT(*) FILTER (WHERE event_type = 'campaign.created') as campaigns_created,
                    COUNT(*) FILTER (WHERE event_type = 'campaign.completed') as campaigns_completed,
                    COUNT(*) FILTER (WHERE event_type = 'campaign.failed') as campaigns_failed,
                    COUNT(*) FILTER (WHERE event_type = 'webhook.received') as webhooks_received,
                    COUNT(*) FILTER (WHERE event_type = 'webhook.processed') as webhooks_processed,
                    COUNT(*) FILTER (WHERE event_type = 'webhook.failed') as webhooks_failed,
                    COUNT(*) FILTER (WHERE event_type = 'recovery.detected') as recoveries_detected,
                    COUNT(*) FILTER (WHERE event_type = 'recovery.completed') as recoveries_completed,
                    COUNT(*) FILTER (WHERE event_type = 'recovery.failed') as recoveries_failed,
                    COUNT(*) FILTER (WHERE event_type = 'rate_limit.allowed') as rate_limit_allowed,
                    COUNT(*) FILTER (WHERE event_type = 'rate_limit.rejected') as rate_limit_rejected,
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
                    rate_limit_allowed = EXCLUDED.rate_limit_allowed,
                    rate_limit_rejected = EXCLUDED.rate_limit_rejected,
                    updated_at = EXCLUDED.updated_at
            """)

            await session.execute(query, {
                "period_start": period_start,
                "period_end": period_end,
                "now": now,
            })
            await session.commit()

            return {"status": "aggregated"}

    return asyncio.run(_run())


@shared_task(bind=True, name="analytics.aggregate_campaigns")
def aggregate_campaign_metrics_task(self, campaign_id: int | None = None) -> dict[str, Any]:
    """
    Celery task to aggregate campaign-level metrics.

    Args:
        campaign_id: Optional specific campaign to aggregate

    Returns:
        dict with count and status
    """
    async def _run():
        from sqlalchemy import text

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            window_start = now - timedelta(hours=1)
            window_end = now

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
                        MAX(duration_ms) FILTER (WHERE event_type = 'message.sent') as max_duration_ms
                    FROM analytics_events
                    WHERE campaign_id IS NOT NULL
                        AND (:campaign_id IS NULL OR campaign_id = :campaign_id)
                        AND occurred_at >= :window_start
                        AND occurred_at < :window_end
                    GROUP BY campaign_id, workspace_id
                )
                INSERT INTO campaign_metrics (
                    campaign_id, workspace_id,
                    sent_count, delivered_count, read_count, failed_count,
                    avg_per_recipient_ms, min_recipient_ms, max_recipient_ms,
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
                    :now
                FROM campaign_stats
                ON CONFLICT (campaign_id) DO UPDATE SET
                    sent_count = EXCLUDED.sent_count,
                    delivered_count = EXCLUDED.delivered_count,
                    read_count = EXCLUDED.read_count,
                    failed_count = EXCLUDED.failed_count,
                    avg_per_recipient_ms = COALESCE(EXCLUDED.avg_per_recipient_ms, campaign_metrics.avg_per_recipient_ms),
                    min_recipient_ms = LEAST(COALESCE(campaign_metrics.min_recipient_ms, 999999), COALESCE(EXCLUDED.min_recipient_ms, 999999)),
                    max_recipient_ms = GREATEST(COALESCE(campaign_metrics.max_recipient_ms, 0), COALESCE(EXCLUDED.max_recipient_ms, 0)),
                    updated_at = EXCLUDED.updated_at
            """)

            result = await session.execute(query, {
                "campaign_id": campaign_id,
                "window_start": window_start,
                "window_end": window_end,
                "now": now,
            })
            await session.commit()

            return {
                "campaign_id": campaign_id,
                "count": result.rowcount,
                "status": "aggregated"
            }

    return asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# Cleanup Tasks
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name="analytics.cleanup")
def cleanup_analytics_task(self) -> dict[str, Any]:
    """
    Celery task to apply retention policies and cleanup old data.

    Returns:
        dict with cleanup counts
    """
    async def _run():
        from sqlalchemy import text

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            counts = {}

            # Raw events retention: 90 days
            cutoff = now - timedelta(days=90)
            query = text("""
                DELETE FROM analytics_events
                WHERE occurred_at < :cutoff
                    AND processed = true
            """)
            result = await session.execute(query, {"cutoff": cutoff})
            counts["raw_events"] = result.rowcount

            # Rollups retention by granularity
            retentions = {
                "1m": 7,
                "5m": 30,
                "1h": 90,
                "1d": 365,
            }

            for granularity, days in retentions.items():
                cutoff = now - timedelta(days=days)
                query = text("""
                    DELETE FROM analytics_rollups
                    WHERE granularity = :granularity
                        AND window_end < :cutoff
                """)
                result = await session.execute(query, {
                    "granularity": granularity,
                    "cutoff": cutoff,
                })
                counts[f"rollups_{granularity}"] = result.rowcount

            await session.commit()
            return {"counts": counts, "status": "cleanup_completed"}

    return asyncio.run(_run())


# ─────────────────────────────────────────────────────────────────────────────
# Scheduled Tasks
# ─────────────────────────────────────────────────────────────────────────────

@shared_task(bind=True, name="analytics.hourly_aggregation")
def hourly_aggregation_task(self) -> dict[str, Any]:
    """
    Hourly aggregation task that runs all aggregation types.

    Returns:
        dict with aggregation results
    """
    from app.services.analytics_aggregation import get_aggregation_manager

    async def _run():
        manager = get_aggregation_manager()
        await manager.start_all()

        # Aggregate for the past hour
        result = await aggregate_rollups_task.delay("1h")

        return {"status": "completed", "result": result}

    return asyncio.run(_run())


@shared_task(bind=True, name="analytics.daily_aggregation")
def daily_aggregation_task(self) -> dict[str, Any]:
    """
    Daily aggregation task for workspace and campaign metrics.

    Returns:
        dict with aggregation results
    """
    async def _run():
        from sqlalchemy import text

        async with get_db_session() as session:
            now = datetime.now(timezone.utc)
            period_start = now.replace(hour=0, minute=0, second=0, microsecond=0) - timedelta(days=1)
            period_end = period_start + timedelta(days=1)

            # Update workspace metrics
            ws_query = text("""
                INSERT INTO workspace_metrics (
                    workspace_id, period_start, period_end,
                    messages_sent, messages_delivered, messages_failed,
                    campaigns_created, campaigns_completed, campaigns_failed,
                    webhooks_received, webhooks_processed, webhooks_failed,
                    recoveries_detected, recoveries_completed, recoveries_failed,
                    rate_limit_allowed, rate_limit_rejected,
                    api_requests, api_errors,
                    created_at, updated_at
                )
                SELECT
                    workspace_id,
                    :period_start,
                    :period_end,
                    COUNT(*) FILTER (WHERE event_type = 'message.sent'),
                    COUNT(*) FILTER (WHERE event_type = 'message.delivered'),
                    COUNT(*) FILTER (WHERE event_type = 'message.failed'),
                    COUNT(*) FILTER (WHERE event_type = 'campaign.created'),
                    COUNT(*) FILTER (WHERE event_type = 'campaign.completed'),
                    COUNT(*) FILTER (WHERE event_type = 'campaign.failed'),
                    COUNT(*) FILTER (WHERE event_type = 'webhook.received'),
                    COUNT(*) FILTER (WHERE event_type = 'webhook.processed'),
                    COUNT(*) FILTER (WHERE event_type = 'webhook.failed'),
                    COUNT(*) FILTER (WHERE event_type = 'recovery.detected'),
                    COUNT(*) FILTER (WHERE event_type = 'recovery.completed'),
                    COUNT(*) FILTER (WHERE event_type = 'recovery.failed'),
                    COUNT(*) FILTER (WHERE event_type = 'rate_limit.allowed'),
                    COUNT(*) FILTER (WHERE event_type = 'rate_limit.rejected'),
                    COUNT(*) FILTER (WHERE event_type = 'api.request'),
                    COUNT(*) FILTER (WHERE event_type = 'api.error'),
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
                    rate_limit_allowed = EXCLUDED.rate_limit_allowed,
                    rate_limit_rejected = EXCLUDED.rate_limit_rejected,
                    api_requests = EXCLUDED.api_requests,
                    api_errors = EXCLUDED.api_errors,
                    updated_at = EXCLUDED.updated_at
            """)

            await session.execute(ws_query, {
                "period_start": period_start,
                "period_end": period_end,
                "now": now,
            })

            await session.commit()
            return {"status": "completed"}

    return asyncio.run(_run())