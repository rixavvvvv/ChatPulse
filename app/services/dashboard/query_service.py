"""
Dashboard query service for ChatPulse analytics.

Provides:
- Campaign delivery metrics
- Workspace usage metrics
- Queue health metrics
- Webhook health metrics
- Retry analytics
- Recovery analytics
- Dashboard overview
- Real-time metrics

All queries support pagination, filtering, date ranges, and aggregation granularity.
Optimized for large workspaces and high event volumes.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.models.analytics import AnalyticsEvent, AnalyticsRollup
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_contact import CampaignContact, DeliveryStatus
from app.models.message_event import MessageEvent, MessageEventStatus
from app.models.message_tracking import MessageTracking, MessageTrackingStatus
from app.models.queue_dead_letter import QueueDeadLetter
from app.models.webhook_ingestion import WebhookIngestion, WebhookIngestionStatus
from app.services.dashboard.cache import CacheKey, get_dashboard_cache
from app.services.dashboard.query_builder import (
    CacheConfig,
    FilterSpec,
    PaginationInput,
    build_pagination,
    compile_filters,
    get_bucket_interval,
    get_comparison_range,
    granularity_to_bucket_seconds,
    granularity_to_trunc_unit,
    resolve_date_range,
    should_use_materialized_view,
    validate_sort_direction,
    validate_sort_field,
)

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Query Service
# ─────────────────────────────────────────────────────────────────────────────


class DashboardQueryService:
    """
    Main dashboard query service.

    Provides all analytics metric queries with:
    - Redis caching (with stale-while-revalidate)
    - Query optimization for large workspaces
    - Pagination support
    - Date range filtering
    - Aggregation granularity
    """

    def __init__(self):
        self._cache = get_dashboard_cache()

    # ─────────────────────────────────────────────────────────────────────────
    # Campaign Delivery Metrics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_campaign_delivery(
        self,
        workspace_id: int,
        campaign_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        granularity: str = "1h",
        include_timeline: bool = True,
        include_error_breakdown: bool = True,
        pagination: PaginationInput | None = None,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get campaign delivery metrics.

        Returns summary stats, timeline, and error breakdown.
        """
        if pagination is None:
            pagination = PaginationInput()

        date_range = resolve_date_range(start_time, end_time, period, default_days=30)
        bucket_interval = get_bucket_interval(granularity, date_range)

        cache_key = CacheKey.build(
            "campaign_delivery",
            workspace_id,
            {
                "campaign_id": campaign_id,
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
                "granularity": bucket_interval,
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            # Build base filters
            conditions = [
                MessageTracking.workspace_id == workspace_id,
            ]
            if campaign_id:
                conditions.append(MessageTracking.campaign_id == campaign_id)
            if date_range.start_time:
                conditions.append(MessageTracking.created_at >= date_range.start_time)
            if date_range.end_time:
                conditions.append(MessageTracking.created_at <= date_range.end_time)

            # Summary counts
            summary_query = select(
                func.count(MessageTracking.id).label("total"),
                func.sum(
                    func.cast(
                        func.extract("epoch", MessageTracking.delivered_at) -
                        func.extract("epoch", MessageTracking.sent_at),
                        float
                    )
                ).label("total_delivery_time"),
                func.count(
                    func.nullif(
                        MessageTracking.current_status.notin_(
                            [MessageTrackingStatus.delivered, MessageTrackingStatus.read]
                        ),
                        False
                    )
                ).label("failed"),
                func.count(
                    func.nullif(
                        MessageTracking.current_status != MessageTrackingStatus.read,
                        False
                    )
                ).label("read"),
            ).where(and_(*conditions))

            result = await session.execute(summary_query)
            row = result.one()

            total = int(row.total or 0)
            failed = int(row.failed or 0)
            delivered = total - failed
            read = int(row.read or 0)
            pending = 0  # Calculated from campaign_contacts

            # Get campaign contact pending counts if campaign specified
            if campaign_id:
                pending_query = select(
                    func.count(CampaignContact.id)
                ).where(
                    and_(
                        CampaignContact.campaign_id == campaign_id,
                        CampaignContact.delivery_status == DeliveryStatus.pending,
                    )
                )
                pending_result = await session.execute(pending_query)
                pending = int(pending_result.scalar() or 0)

            # Timeline data
            timeline = []
            if include_timeline:
                trunc_unit = granularity_to_trunc_unit(bucket_interval)
                timeline_query = select(
                    func.date_trunc(trunc_unit, MessageTracking.created_at).label("bucket"),
                    MessageTracking.current_status,
                    func.count(MessageTracking.id).label("count"),
                ).where(and_(*conditions)).group_by(
                    "bucket",
                    MessageTracking.current_status,
                ).order_by("bucket")

                timeline_result = await session.execute(timeline_query)
                timeline_rows = timeline_result.all()

                # Group by bucket
                buckets: dict[datetime, dict] = {}
                for row in timeline_rows:
                    bucket: datetime = row.bucket
                    if bucket not in buckets:
                        buckets[bucket] = {"timestamp": bucket, "sent": 0, "delivered": 0, "read": 0, "failed": 0}
                    status = row.current_status
                    count = int(row.count or 0)
                    if status == MessageTrackingStatus.sent:
                        buckets[bucket]["sent"] += count
                    elif status == MessageTrackingStatus.delivered:
                        buckets[bucket]["delivered"] += count
                    elif status == MessageTrackingStatus.read:
                        buckets[bucket]["read"] += count
                    elif status == MessageTrackingStatus.failed:
                        buckets[bucket]["failed"] += count

                timeline = list(buckets.values())

            # Error breakdown
            error_breakdown = {}
            if include_error_breakdown:
                error_query = select(
                    func.left(MessageTracking.last_error, 100).label("error"),
                    func.count(MessageTracking.id).label("count"),
                ).where(
                    and_(
                        *conditions,
                        MessageTracking.current_status == MessageTrackingStatus.failed,
                        MessageTracking.last_error.isnot(None),
                    )
                ).group_by("error").order_by(
                    func.count(MessageTracking.id).desc()
                ).limit(20)

                error_result = await session.execute(error_query)
                for row in error_result:
                    error_breakdown[row.error or "Unknown"] = int(row.count or 0)

            # Delivery rates
            delivery_rate = (delivered / total * 100) if total > 0 else 0.0
            read_rate = (read / total * 100) if total > 0 else 0.0
            failure_rate = (failed / total * 100) if total > 0 else 0.0
            avg_delivery_time = (float(row.total_delivery_time) / delivered) if delivered > 0 else None

            response = {
                "summary": {
                    "campaign_id": campaign_id,
                    "workspace_id": workspace_id,
                    "total_recipients": total,
                    "sent_count": total,
                    "delivered_count": delivered,
                    "read_count": read,
                    "failed_count": failed,
                    "pending_count": pending,
                    "delivery_rate": round(delivery_rate, 2),
                    "read_rate": round(read_rate, 2),
                    "failure_rate": round(failure_rate, 2),
                    "avg_time_to_deliver_ms": (avg_delivery_time * 1000) if avg_delivery_time else None,
                },
                "timeline": timeline,
                "error_breakdown": error_breakdown,
                "start_time": date_range.start_time,
                "end_time": date_range.end_time,
                "duration_seconds": (date_range.end_time - date_range.start_time).total_seconds(),
                "pagination": build_pagination(
                    limit=pagination.limit,
                    offset=pagination.offset,
                    total=total,
                ).model_dump(),
            }

            await self._cache.set(cache_key, response, "campaign_delivery")
            return response

    async def get_campaign_delivery_list(
        self,
        workspace_id: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        pagination: PaginationInput | None = None,
        sort_by: str = "created_at",
        sort_dir: str = "desc",
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get list of campaigns with delivery metrics."""
        if pagination is None:
            pagination = PaginationInput()

        date_range = resolve_date_range(start_time, end_time, period, default_days=30)

        cache_key = CacheKey.build(
            "campaign_delivery_list",
            workspace_id,
            {
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
                "sort_by": sort_by,
                "sort_dir": sort_dir,
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            # Count query
            count_query = select(func.count(Campaign.id)).where(
                Campaign.workspace_id == workspace_id
            )
            count_result = await session.execute(count_query)
            total = int(count_result.scalar() or 0)

            # Main query with aggregates
            sort_field = validate_sort_field(sort_by)
            sort_direction = validate_sort_direction(sort_dir)

            query = (
                select(
                    Campaign.id,
                    Campaign.name,
                    Campaign.status,
                    Campaign.created_at,
                    Campaign.success_count,
                    Campaign.failed_count,
                    func.count(CampaignContact.id).label("total_recipients"),
                )
                .outerjoin(
                    CampaignContact,
                    CampaignContact.campaign_id == Campaign.id,
                )
                .where(Campaign.workspace_id == workspace_id)
                .group_by(Campaign.id)
                .order_by(
                    getattr(Campaign, sort_field).desc()
                    if sort_direction == "desc"
                    else getattr(Campaign, sort_field).asc()
                )
                .limit(pagination.limit)
                .offset(pagination.offset)
            )

            result = await session.execute(query)
            campaigns = []
            for row in result.all():
                total_rec = int(row.total_recipients or 0)
                success = int(row.success_count or 0)
                failed = int(row.failed_count or 0)
                campaigns.append({
                    "campaign_id": row.id,
                    "workspace_id": workspace_id,
                    "campaign_name": row.name,
                    "status": row.status.value if row.status else None,
                    "created_at": row.created_at.isoformat() if row.created_at else None,
                    "total_recipients": total_rec,
                    "sent_count": success + failed,
                    "delivered_count": success,
                    "failed_count": failed,
                    "delivery_rate": round((success / total_rec * 100) if total_rec > 0 else 0, 2),
                    "failure_rate": round((failed / total_rec * 100) if total_rec > 0 else 0, 2),
                })

            response = {
                "items": campaigns,
                "total": total,
                "limit": pagination.limit,
                "offset": pagination.offset,
                "has_more": (pagination.offset + pagination.limit) < total,
            }

            await self._cache.set(cache_key, response, "campaign_delivery")
            return response

    # ─────────────────────────────────────────────────────────────────────────
    # Workspace Usage Metrics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_workspace_usage(
        self,
        workspace_id: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        granularity: str = "1d",
        include_timeline: bool = True,
        include_top_campaigns: bool = True,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """
        Get workspace usage metrics.

        Includes message counts, campaign stats, contact metrics.
        """
        date_range = resolve_date_range(start_time, end_time, period, default_days=30)
        bucket_interval = get_bucket_interval(granularity, date_range)

        cache_key = CacheKey.build(
            "workspace_usage",
            workspace_id,
            {
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
                "granularity": bucket_interval,
                "include_timeline": include_timeline,
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            # Message summary
            msg_conditions = [
                MessageTracking.workspace_id == workspace_id,
                MessageTracking.created_at >= date_range.start_time,
                MessageTracking.created_at <= date_range.end_time,
            ]

            msg_query = select(
                func.count(MessageTracking.id).label("total"),
                func.count(
                    func.nullif(
                        MessageTracking.current_status.in_(
                            [MessageTrackingStatus.delivered, MessageTrackingStatus.read]
                        ),
                        False
                    )
                ).label("delivered"),
                func.count(
                    func.nullif(
                        MessageTracking.current_status != MessageTrackingStatus.read,
                        False
                    )
                ).label("read"),
                func.count(
                    func.nullif(
                        MessageTracking.current_status == MessageTrackingStatus.failed,
                        False
                    )
                ).label("failed"),
            ).where(and_(*msg_conditions))

            msg_result = await session.execute(msg_query)
            msg_row = msg_result.one()
            messages_sent = int(msg_row.total or 0)
            messages_delivered = int(msg_row.delivered or 0)
            messages_failed = int(msg_row.failed or 0)
            messages_read = int(msg_row.read or 0)

            # Campaign summary
            camp_conditions = [
                Campaign.workspace_id == workspace_id,
                Campaign.created_at >= date_range.start_time,
                Campaign.created_at <= date_range.end_time,
            ]
            camp_query = select(
                func.count(Campaign.id).label("created"),
                func.count(
                    func.nullif(Campaign.status == CampaignStatus.completed, False)
                ).label("completed"),
                func.count(
                    func.nullif(Campaign.status == CampaignStatus.failed, False)
                ).label("failed"),
                func.count(
                    func.nullif(Campaign.status == CampaignStatus.running, False)
                ).label("active"),
            ).where(and_(*camp_conditions))

            camp_result = await session.execute(camp_query)
            camp_row = camp_result.one()
            campaigns_created = int(camp_row.created or 0)
            campaigns_completed = int(camp_row.completed or 0)
            campaigns_failed = int(camp_row.failed or 0)
            campaigns_active = int(camp_row.active or 0)

            # Timeline
            timeline = []
            if include_timeline:
                trunc_unit = granularity_to_trunc_unit(bucket_interval)
                timeline_query = select(
                    func.date_trunc(trunc_unit, MessageTracking.created_at).label("bucket"),
                    func.count(MessageTracking.id).label("count"),
                ).where(and_(*msg_conditions)).group_by("bucket").order_by("bucket")

                timeline_result = await session.execute(timeline_query)
                for row in timeline_result.all():
                    timeline.append({
                        "timestamp": row.bucket.isoformat() if row.bucket else None,
                        "messages_sent": int(row.count or 0),
                        "messages_delivered": 0,
                        "api_requests": 0,
                        "active_campaigns": campaigns_active,
                    })

            # Top campaigns
            top_campaigns = []
            if include_top_campaigns:
                top_query = (
                    select(
                        Campaign.id,
                        Campaign.name,
                        Campaign.success_count,
                        Campaign.failed_count,
                    )
                    .where(Campaign.workspace_id == workspace_id)
                    .order_by(Campaign.success_count.desc())
                    .limit(5)
                )
                top_result = await session.execute(top_query)
                for row in top_result.all():
                    total_rec = int(row.success_count or 0) + int(row.failed_count or 0)
                    top_campaigns.append({
                        "campaign_id": row.id,
                        "campaign_name": row.name,
                        "sent_count": int(row.success_count or 0) + int(row.failed_count or 0),
                        "failed_count": int(row.failed_count or 0),
                        "delivery_rate": round((int(row.success_count or 0) / total_rec * 100) if total_rec > 0 else 0, 2),
                    })

            response = {
                "summary": {
                    "workspace_id": workspace_id,
                    "period": date_range.period,
                    "messages_sent": messages_sent,
                    "messages_delivered": messages_delivered,
                    "messages_failed": messages_failed,
                    "messages_read": messages_read,
                    "delivery_rate": round((messages_delivered / messages_sent * 100) if messages_sent > 0 else 0, 2),
                    "read_rate": round((messages_read / messages_sent * 100) if messages_sent > 0 else 0, 2),
                    "failure_rate": round((messages_failed / messages_sent * 100) if messages_sent > 0 else 0, 2),
                    "campaigns_created": campaigns_created,
                    "campaigns_completed": campaigns_completed,
                    "campaigns_failed": campaigns_failed,
                    "campaigns_active": campaigns_active,
                },
                "timeline": timeline,
                "top_campaigns": top_campaigns,
                "start_time": date_range.start_time,
                "end_time": date_range.end_time,
            }

            await self._cache.set(cache_key, response, "workspace_usage")
            return response

    # ─────────────────────────────────────────────────────────────────────────
    # Queue Health Metrics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_queue_health(
        self,
        workspace_id: int,
        queue_name: str | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        include_timeline: bool = True,
        include_worker_breakdown: bool = True,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get queue health metrics from analytics events and dead letters."""
        date_range = resolve_date_range(start_time, end_time, period, default_days=7)

        cache_key = CacheKey.build(
            "queue_health",
            workspace_id,
            {
                "queue_name": queue_name,
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            # Get queue task events
            conditions = [
                AnalyticsEvent.workspace_id == workspace_id,
                AnalyticsEvent.event_category == "queue",
                AnalyticsEvent.occurred_at >= date_range.start_time,
                AnalyticsEvent.occurred_at <= date_range.end_time,
            ]
            if queue_name:
                conditions.append(AnalyticsEvent.queue_name == queue_name)

            summary_query = select(
                AnalyticsEvent.event_type,
                func.count(AnalyticsEvent.id).label("count"),
                func.avg(AnalyticsEvent.duration_ms).label("avg_duration"),
                func.percentile_cont(0.95).within_group(
                    AnalyticsEvent.duration_ms
                ).label("p95_duration"),
            ).where(and_(*conditions)).group_by(AnalyticsEvent.event_type)

            summary_result = await session.execute(summary_query)
            started = completed = failed = retried = 0
            avg_process = p95_process = 0.0
            for row in summary_result.all():
                count = int(row.count or 0)
                if row.event_type == "queue.task.started":
                    started = count
                elif row.event_type == "queue.task.completed":
                    completed = count
                elif row.event_type == "queue.task.failed":
                    failed = count
                avg_process = float(row.avg_duration or 0)
                p95_process = float(row.p95_duration or 0)

            # Dead letter queue stats
            dlq_query = select(
                func.count(QueueDeadLetter.id).label("total"),
                func.count(
                    func.nullif(QueueDeadLetter.replayed_at.is_(None), False)
                ).label("replayed"),
            ).where(
                QueueDeadLetter.created_at >= date_range.start_time,
                QueueDeadLetter.created_at <= date_range.end_time,
            )
            dlq_result = await session.execute(dlq_query)
            dlq_row = dlq_result.one()
            tasks_failed = int(dlq_row.total or 0)
            tasks_retried = int(dlq_row.replayed or 0)

            tasks_pending = max(0, started - completed - tasks_failed)
            total_tasks = max(1, completed + tasks_failed)

            success_rate = round((completed / total_tasks * 100), 2)
            failure_rate = round((tasks_failed / total_tasks * 100), 2)

            # Timeline
            timeline = []
            if include_timeline:
                trunc_unit = granularity_to_trunc_unit("1h")
                timeline_query = select(
                    func.date_trunc(trunc_unit, AnalyticsEvent.occurred_at).label("bucket"),
                    AnalyticsEvent.event_type,
                    func.count(AnalyticsEvent.id).label("count"),
                ).where(and_(*conditions)).group_by("bucket", AnalyticsEvent.event_type).order_by("bucket")

                tl_result = await session.execute(timeline_query)
                buckets: dict[datetime, dict] = {}
                for row in tl_result.all():
                    bucket = row.bucket
                    if bucket not in buckets:
                        buckets[bucket] = {"timestamp": bucket, "queue_depth": 0, "tasks_completed": 0, "tasks_failed": 0, "active_workers": 0}
                    if row.event_type == "queue.task.completed":
                        buckets[bucket]["tasks_completed"] = int(row.count or 0)
                    elif row.event_type == "queue.task.failed":
                        buckets[bucket]["tasks_failed"] = int(row.count or 0)

                timeline = list(buckets.values())

            # Worker breakdown
            worker_breakdown = {}
            if include_worker_breakdown:
                worker_query = select(
                    AnalyticsEvent.worker_id,
                    func.count(AnalyticsEvent.id).label("count"),
                ).where(
                    and_(*conditions, AnalyticsEvent.worker_id.isnot(None))
                ).group_by(AnalyticsEvent.worker_id).order_by(
                    func.count(AnalyticsEvent.id).desc()
                ).limit(20)

                worker_result = await session.execute(worker_query)
                for row in worker_result.all():
                    worker_breakdown[row.worker_id or "unknown"] = int(row.count or 0)

            response = {
                "summary": {
                    "workspace_id": workspace_id,
                    "queue_name": queue_name or "all",
                    "tasks_pending": tasks_pending,
                    "tasks_in_progress": 0,
                    "tasks_completed": completed,
                    "tasks_failed": tasks_failed,
                    "tasks_retried": tasks_retried,
                    "success_rate": success_rate,
                    "failure_rate": failure_rate,
                    "retry_rate": round((tasks_retried / total_tasks * 100) if total_tasks > 0 else 0, 2),
                    "avg_process_time_ms": avg_process,
                    "p95_process_time_ms": p95_process,
                    "p99_process_time_ms": None,
                    "queue_depth": tasks_pending,
                    "active_workers": len(worker_breakdown),
                },
                "timeline": timeline,
                "error_breakdown": {},
                "by_worker": worker_breakdown,
            }

            await self._cache.set(cache_key, response, "queue_health")
            return response

    # ─────────────────────────────────────────────────────────────────────────
    # Webhook Health Metrics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_webhook_health(
        self,
        workspace_id: int,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        include_timeline: bool = True,
        include_recent_failures: bool = True,
        limit_recent_failures: int = 10,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get webhook health metrics."""
        date_range = resolve_date_range(start_time, end_time, period, default_days=7)

        cache_key = CacheKey.build(
            "webhook_health",
            workspace_id,
            {
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            conditions = [
                WebhookIngestion.workspace_id == workspace_id,
                WebhookIngestion.received_at >= date_range.start_time,
                WebhookIngestion.received_at <= date_range.end_time,
            ]

            # Summary
            summary_query = select(
                func.count(WebhookIngestion.id).label("total"),
                func.count(
                    func.nullif(WebhookIngestion.processing_status != WebhookIngestionStatus.completed.value, False)
                ).label("processed"),
                func.count(
                    func.nullif(WebhookIngestion.processing_status == WebhookIngestionStatus.failed.value, False)
                ).label("failed"),
                func.count(
                    func.nullif(WebhookIngestion.processing_status == WebhookIngestionStatus.received.value, False)
                ).label("pending"),
            ).where(and_(*conditions))

            result = await session.execute(summary_query)
            row = result.one()
            received = int(row.total or 0)
            processed = int(row.processed or 0)
            failed = int(row.failed or 0)
            pending = int(row.pending or 0)

            # By source
            source_query = select(
                WebhookIngestion.source,
                func.count(WebhookIngestion.id).label("count"),
            ).where(and_(*conditions)).group_by(WebhookIngestion.source)

            source_result = await session.execute(source_query)
            by_source = {r.source: int(r.count or 0) for r in source_result.all()}

            # Timeline
            timeline = []
            if include_timeline:
                trunc_unit = granularity_to_trunc_unit("1h")
                timeline_query = select(
                    func.date_trunc(trunc_unit, WebhookIngestion.received_at).label("bucket"),
                    func.count(WebhookIngestion.id).label("count"),
                ).where(and_(*conditions)).group_by("bucket").order_by("bucket")

                tl_result = await session.execute(timeline_query)
                for row in tl_result.all():
                    timeline.append({
                        "timestamp": row.bucket.isoformat() if row.bucket else None,
                        "received": int(row.count or 0),
                        "processed": 0,
                        "failed": 0,
                    })

            # Recent failures
            recent_failures = []
            if include_recent_failures:
                failure_query = (
                    select(
                        WebhookIngestion.id,
                        WebhookIngestion.source,
                        WebhookIngestion.error_message,
                        WebhookIngestion.received_at,
                        WebhookIngestion.replay_count,
                    )
                    .where(
                        and_(*conditions, WebhookIngestion.processing_status == WebhookIngestionStatus.failed.value)
                    )
                    .order_by(WebhookIngestion.received_at.desc())
                    .limit(limit_recent_failures)
                )

                fail_result = await session.execute(failure_query)
                for row in fail_result.all():
                    recent_failures.append({
                        "webhook_id": row.id,
                        "source": row.source,
                        "error_type": "webhook_processing_error",
                        "error_message": row.error_message,
                        "received_at": row.received_at.isoformat() if row.received_at else None,
                        "retry_count": int(row.replay_count or 0),
                    })

            response = {
                "summary": {
                    "workspace_id": workspace_id,
                    "webhooks_received": received,
                    "webhooks_processed": processed,
                    "webhooks_failed": failed,
                    "webhooks_pending": pending,
                    "success_rate": round((processed / received * 100) if received > 0 else 0, 2),
                    "failure_rate": round((failed / received * 100) if received > 0 else 0, 2),
                },
                "timeline": timeline,
                "recent_failures": recent_failures,
                "by_source": by_source,
            }

            await self._cache.set(cache_key, response, "webhook_health")
            return response

    # ─────────────────────────────────────────────────────────────────────────
    # Retry Analytics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_retry_analytics(
        self,
        workspace_id: int,
        campaign_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        include_timeline: bool = True,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get retry analytics from message events."""
        date_range = resolve_date_range(start_time, end_time, period, default_days=30)

        cache_key = CacheKey.build(
            "retry_analytics",
            workspace_id,
            {
                "campaign_id": campaign_id,
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            conditions = [
                MessageTracking.workspace_id == workspace_id,
                MessageTracking.updated_at >= date_range.start_time,
                MessageTracking.updated_at <= date_range.end_time,
                MessageTracking.attempt_count > 1,
            ]
            if campaign_id:
                conditions.append(MessageTracking.campaign_id == campaign_id)

            # Retry summary
            retry_query = select(
                func.count(MessageTracking.id).label("total_retries"),
                func.count(
                    func.nullif(MessageTracking.current_status != MessageTrackingStatus.failed, False)
                ).label("retry_failures"),
                func.avg(MessageTracking.attempt_count).label("avg_attempts"),
            ).where(and_(*conditions))

            retry_result = await session.execute(retry_query)
            row = retry_result.one()
            total_retries = int(row.total_retries or 0)
            retry_failures = int(row.retry_failures or 0)
            retry_successes = total_retries - retry_failures

            # Error breakdown
            error_query = select(
                func.left(MessageTracking.last_error, 100).label("error"),
                func.count(MessageTracking.id).label("count"),
            ).where(
                and_(*conditions, MessageTracking.current_status == MessageTrackingStatus.failed)
            ).group_by("error").order_by(func.count(MessageTracking.id).desc()).limit(10)

            error_result = await session.execute(error_query)
            error_breakdown = {r.error or "Unknown": int(r.count or 0) for r in error_result.all()}

            # Timeline
            timeline = []
            if include_timeline:
                trunc_unit = granularity_to_trunc_unit("1d")
                timeline_query = select(
                    func.date_trunc(trunc_unit, MessageTracking.updated_at).label("bucket"),
                    func.count(MessageTracking.id).label("count"),
                ).where(and_(*conditions)).group_by("bucket").order_by("bucket")

                tl_result = await session.execute(timeline_query)
                for row in tl_result.all():
                    timeline.append({
                        "timestamp": row.bucket.isoformat() if row.bucket else None,
                        "retry_attempts": int(row.count or 0),
                        "retry_successes": 0,
                        "retry_failures": 0,
                    })

            response = {
                "summary": {
                    "workspace_id": workspace_id,
                    "total_retries": total_retries,
                    "retry_success_count": retry_successes,
                    "retry_failure_count": retry_failures,
                    "retry_rate": round((total_retries / max(1, total_retries + (await self._get_total_messages(session, workspace_id, date_range)))) * 100, 2),
                    "retry_success_rate": round((retry_successes / total_retries * 100) if total_retries > 0 else 0, 2),
                    "max_retry_attempts": 4,
                },
                "timeline": timeline,
                "top_retry_error_types": [
                    {"error_type": k, "count": v, "retry_rate": 0, "success_after_retry": 0}
                    for k, v in list(error_breakdown.items())[:5]
                ],
                "by_error_type": error_breakdown,
            }

            await self._cache.set(cache_key, response, "retry_analytics")
            return response

    async def _get_total_messages(self, session: AsyncSession, workspace_id: int, date_range) -> int:
        """Helper to get total message count."""
        query = select(func.count(MessageTracking.id)).where(
            MessageTracking.workspace_id == workspace_id,
            MessageTracking.created_at >= date_range.start_time,
            MessageTracking.created_at <= date_range.end_time,
        )
        result = await session.execute(query)
        return int(result.scalar() or 0)

    # ─────────────────────────────────────────────────────────────────────────
    # Recovery Analytics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_recovery_analytics(
        self,
        workspace_id: int,
        campaign_id: int | None = None,
        start_time: datetime | None = None,
        end_time: datetime | None = None,
        period: str | None = None,
        include_timeline: bool = True,
        include_recent_recoveries: bool = True,
        limit_recent_recoveries: int = 10,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get recovery analytics."""
        date_range = resolve_date_range(start_time, end_time, period, default_days=30)

        cache_key = CacheKey.build(
            "recovery_analytics",
            workspace_id,
            {
                "campaign_id": campaign_id,
                "start": date_range.start_time.isoformat(),
                "end": date_range.end_time.isoformat(),
            },
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            conditions = [
                AnalyticsEvent.workspace_id == workspace_id,
                AnalyticsEvent.event_category == "recovery",
                AnalyticsEvent.occurred_at >= date_range.start_time,
                AnalyticsEvent.occurred_at <= date_range.end_time,
            ]

            summary_query = select(
                AnalyticsEvent.event_type,
                func.count(AnalyticsEvent.id).label("count"),
            ).where(and_(*conditions)).group_by(AnalyticsEvent.event_type)

            result = await session.execute(summary_query)
            detected = started = completed = failed = 0
            for row in result.all():
                count = int(row.count or 0)
                if row.event_type == "recovery.detected":
                    detected = count
                elif row.event_type == "recovery.started":
                    started = count
                elif row.event_type == "recovery.completed":
                    completed = count
                elif row.event_type == "recovery.failed":
                    failed = count

            # Recent recoveries from campaigns with recovery data
            recent_recoveries = []
            if include_recent_recoveries:
                rec_query = (
                    select(
                        Campaign.id,
                        Campaign.name,
                        Campaign.status,
                        Campaign.last_recovered_at,
                        Campaign.recovery_count,
                        Campaign.created_at,
                    )
                    .where(
                        and_(
                            Campaign.workspace_id == workspace_id,
                            Campaign.recovery_count > 0,
                        )
                    )
                    .order_by(Campaign.last_recovered_at.desc())
                    .limit(limit_recent_recoveries)
                )

                rec_result = await session.execute(rec_query)
                for row in rec_result.all():
                    recent_recoveries.append({
                        "recovery_id": 0,
                        "campaign_id": row.id,
                        "status": row.status.value if row.status else None,
                        "detected_at": row.created_at.isoformat() if row.created_at else None,
                        "started_at": row.last_recovered_at.isoformat() if row.last_recovered_at else None,
                        "completed_at": None,
                        "messages_to_recover": 0,
                        "messages_recovered": 0,
                        "recovery_attempts": int(row.recovery_count or 0),
                    })

            response = {
                "summary": {
                    "workspace_id": workspace_id,
                    "recoveries_detected": detected,
                    "recoveries_started": started,
                    "recoveries_completed": completed,
                    "recoveries_failed": failed,
                    "recovered_messages": 0,
                    "recovered_campaigns": completed,
                    "recovery_rate": round((completed / started * 100) if started > 0 else 0, 2),
                    "success_rate": round((completed / (completed + failed) * 100) if (completed + failed) > 0 else 0, 2),
                },
                "timeline": [],
                "recent_recoveries": recent_recoveries,
            }

            await self._cache.set(cache_key, response, "recovery_analytics")
            return response

    # ─────────────────────────────────────────────────────────────────────────
    # Dashboard Overview
    # ─────────────────────────────────────────────────────────────────────────

    async def get_dashboard_overview(
        self,
        workspace_id: int,
        period: str = "today",
        compare_previous: bool = False,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get dashboard overview with summary metrics."""
        date_range = resolve_date_range(period=period, default_days=1)

        cache_key = CacheKey.build(
            "dashboard_overview",
            workspace_id,
            {"period": period, "compare": compare_previous},
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        # Get current period
        current = await self.get_workspace_usage(
            workspace_id=workspace_id,
            start_time=date_range.start_time,
            end_time=date_range.end_time,
            period=period,
            include_timeline=False,
            include_top_campaigns=True,
            use_cache=False,
        )

        summary = current["summary"]

        # Get previous period for comparison
        previous = None
        changes = {}
        if compare_previous:
            comp_range = get_comparison_range(date_range)
            prev_data = await self.get_workspace_usage(
                workspace_id=workspace_id,
                start_time=comp_range.start_time,
                end_time=comp_range.end_time,
                include_timeline=False,
                use_cache=False,
            )
            previous = prev_data["summary"]

            # Calculate changes
            for key in ["messages_sent", "messages_delivered", "campaigns_created"]:
                curr_val = summary.get(key, 0)
                prev_val = previous.get(key, 0)
                if prev_val > 0:
                    change = ((curr_val - prev_val) / prev_val) * 100
                else:
                    change = 100.0 if curr_val > 0 else 0.0
                changes[key] = round(change, 2)

        response = {
            "workspace_id": workspace_id,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "period": period,
            "period_start": date_range.start_time.isoformat(),
            "period_end": date_range.end_time.isoformat(),
            "total_messages_sent": summary.get("messages_sent", 0),
            "total_messages_delivered": summary.get("messages_delivered", 0),
            "total_campaigns": summary.get("campaigns_created", 0),
            "campaigns_completed": summary.get("campaigns_completed", 0),
            "campaigns_active": summary.get("campaigns_active", 0),
            "delivery_rate": summary.get("delivery_rate", 0),
            "read_rate": summary.get("read_rate", 0),
            "error_rate": summary.get("failure_rate", 0),
            "queue_depth": 0,
            "active_workers": 0,
            "health_score": self._calculate_health_score(summary),
            "changes": changes,
        }

        await self._cache.set(cache_key, response, "dashboard_overview")
        return response

    def _calculate_health_score(self, summary: dict) -> float:
        """Calculate overall health score (0-100) based on metrics."""
        score = 100.0

        # Deduct for poor delivery rate
        delivery_rate = summary.get("delivery_rate", 100)
        if delivery_rate < 90:
            score -= (90 - delivery_rate) * 0.5

        # Deduct for high failure rate
        failure_rate = summary.get("failure_rate", 0)
        if failure_rate > 5:
            score -= failure_rate * 2

        return max(0.0, min(100.0, round(score, 1)))

    # ─────────────────────────────────────────────────────────────────────────
    # Real-time Metrics
    # ─────────────────────────────────────────────────────────────────────────

    async def get_realtime_metrics(
        self,
        workspace_id: int,
        use_cache: bool = True,
    ) -> dict[str, Any]:
        """Get real-time metrics with minimal caching."""
        cache_key = CacheKey.build_realtime(workspace_id)

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        async with get_db_session() as session:
            # Active campaigns
            active_query = select(func.count(Campaign.id)).where(
                and_(
                    Campaign.workspace_id == workspace_id,
                    Campaign.status == CampaignStatus.running,
                )
            )
            active_result = await session.execute(active_query)
            active_campaigns = int(active_result.scalar() or 0)

            # Messages in flight (sent but not delivered/failed)
            inflight_query = select(func.count(MessageTracking.id)).where(
                and_(
                    MessageTracking.workspace_id == workspace_id,
                    MessageTracking.current_status == MessageTrackingStatus.sent,
                    MessageTracking.sent_at >= datetime.now(timezone.utc) - timedelta(minutes=5),
                )
            )
            inflight_result = await session.execute(inflight_query)
            messages_in_flight = int(inflight_result.scalar() or 0)

            # Messages last minute
            minute_query = select(func.count(MessageTracking.id)).where(
                and_(
                    MessageTracking.workspace_id == workspace_id,
                    MessageTracking.created_at >= datetime.now(timezone.utc) - timedelta(minutes=1),
                )
            )
            minute_result = await session.execute(minute_query)
            messages_last_minute = int(minute_result.scalar() or 0)

            response = {
                "workspace_id": workspace_id,
                "updated_at": datetime.now(timezone.utc).isoformat(),
                "active_campaigns": active_campaigns,
                "messages_in_flight": messages_in_flight,
                "messages_per_second": round(messages_last_minute / 60, 2),
                "messages_last_minute": messages_last_minute,
                "queue_depth": messages_in_flight,
                "error_rate_percent": 0.0,
            }

            await self._cache.set(cache_key, response, "realtime")
            return response

    # ─────────────────────────────────────────────────────────────────────────
    # Alerts
    # ─────────────────────────────────────────────────────────────────────────

    async def get_alerts(
        self,
        workspace_id: int,
        severity_threshold: str = "warning",
        use_cache: bool = True,
    ) -> list[dict[str, Any]]:
        """Generate alerts based on metric thresholds."""
        cache_key = CacheKey.build(
            "alerts",
            workspace_id,
            {"severity": severity_threshold},
        )

        if use_cache:
            entry = await self._cache.get(cache_key)
            if entry and entry.is_fresh():
                return entry.data

        alerts = []

        # Check delivery rate
        usage = await self.get_workspace_usage(
            workspace_id,
            period="today",
            include_timeline=False,
            use_cache=True,
        )
        summary = usage["summary"]
        delivery_rate = summary.get("delivery_rate", 100)

        if delivery_rate < 80:
            alerts.append({
                "alert_id": f"delivery_rate_low_{workspace_id}",
                "severity": "critical" if delivery_rate < 60 else "warning",
                "message": f"Delivery rate is {delivery_rate}%, below 80% threshold",
                "metric_name": "delivery_rate",
                "current_value": delivery_rate,
                "threshold": 80.0,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

        await self._cache.set(cache_key, alerts, "dashboard_overview", compute_time_ms=0)
        return alerts
