"""
Metrics hooks for integrating into services.

Provides metrics collection for:
- Queue workers
- Webhook processing
- Dispatch service
- Campaign runtime
- Recovery system
"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from functools import wraps
from typing import Any, Callable

from app.metrics import (
    MetricName,
    MetricType,
    get_metrics,
    record_gauge,
    record_histogram,
    increment_counter,
)


# ─────────────────────────────────────────────────────────────────────────────
# Queue Worker Metrics
# ─────────────────────────────────────────────────────────────────────────────

class QueueWorkerMetrics:
    """Metrics for Celery queue workers."""

    @staticmethod
    async def record_task_start(
        task_name: str,
        task_id: str,
        queue_name: str,
        worker_id: str | None = None,
    ) -> None:
        """Record task start."""
        metrics = get_metrics()
        labels = {"task_name": task_name, "queue_name": queue_name}
        if worker_id:
            labels["worker_id"] = worker_id

        await metrics.record_gauge(
            MetricName.QUEUE_DEPTH,
            1,
            labels,
        )
        await metrics.increment_counter(
            f"{task_name}.started",
            labels=labels,
        )

    @staticmethod
    async def record_task_complete(
        task_name: str,
        task_id: str,
        duration_ms: float,
        queue_name: str,
        success: bool = True,
        worker_id: str | None = None,
    ) -> None:
        """Record task completion."""
        metrics = get_metrics()
        labels = {"task_name": task_name, "queue_name": queue_name, "status": "success" if success else "failed"}
        if worker_id:
            labels["worker_id"] = worker_id

        await metrics.record_histogram(
            MetricName.QUEUE_TASK_DURATION,
            duration_ms,
            labels,
        )
        await metrics.increment_counter(
            f"{task_name}.completed",
            labels={**labels, "status": "success" if success else "failed"},
        )

    @staticmethod
    async def record_task_error(
        task_name: str,
        task_id: str,
        error_type: str,
        queue_name: str,
        worker_id: str | None = None,
    ) -> None:
        """Record task error."""
        metrics = get_metrics()
        labels = {
            "task_name": task_name,
            "queue_name": queue_name,
            "error_type": error_type,
        }
        if worker_id:
            labels["worker_id"] = worker_id

        await metrics.increment_counter(
            MetricName.WORKER_ERROR,
            labels=labels,
        )

    @staticmethod
    async def record_task_retry(
        task_name: str,
        attempt: int,
        queue_name: str,
    ) -> None:
        """Record task retry."""
        await increment_counter(
            f"{task_name}.retry",
            labels={"task_name": task_name, "queue_name": queue_name, "attempt": str(attempt)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Processing Metrics
# ─────────────────────────────────────────────────────────────────────────────

class WebhookMetrics:
    """Metrics for webhook processing."""

    @staticmethod
    async def record_webhook_received(
        source: str,
        event_type: str,
        payload_size: int,
    ) -> None:
        """Record incoming webhook."""
        await increment_counter(
            MetricName.WEBHOOK_RECEIVED,
            labels={"source": source, "event_type": event_type},
        )

    @staticmethod
    async def record_webhook_processed(
        source: str,
        event_type: str,
        duration_ms: float,
        success: bool = True,
        workspace_id: int | None = None,
    ) -> None:
        """Record webhook processing completion."""
        labels = {"source": source, "event_type": event_type, "status": "success" if success else "failed"}
        if workspace_id:
            labels["workspace_id"] = str(workspace_id)

        await record_histogram(
            MetricName.WEBHOOK_LATENCY,
            duration_ms,
            labels=labels,
        )
        await increment_counter(
            MetricName.WEBHOOK_PROCESSED if success else MetricName.WEBHOOK_FAILED,
            labels=labels,
        )


# ─────────────────────────────────────────────────────────────────────────────
# Campaign Runtime Metrics
# ─────────────────────────────────────────────────────────────────────────────

class CampaignMetrics:
    """Metrics for campaign execution."""

    @staticmethod
    async def record_campaign_created(
        campaign_id: int,
        workspace_id: int,
        recipient_count: int,
    ) -> None:
        """Record campaign creation."""
        await increment_counter(
            MetricName.CAMPAIGN_CREATED,
            labels={"workspace_id": str(workspace_id)},
        )
        await record_gauge(
            MetricName.CAMPAIGN_RECIPIENTS_TOTAL,
            recipient_count,
            labels={"campaign_id": str(campaign_id), "workspace_id": str(workspace_id)},
        )

    @staticmethod
    async def record_campaign_started(
        campaign_id: int,
        workspace_id: int,
    ) -> None:
        """Record campaign start."""
        await increment_counter(
            "campaign.send.started",
            labels={"workspace_id": str(workspace_id), "campaign_id": str(campaign_id)},
        )

    @staticmethod
    async def record_campaign_progress(
        campaign_id: int,
        workspace_id: int,
        processed: int,
        total: int,
        success_count: int,
        failed_count: int,
    ) -> None:
        """Record campaign progress."""
        labels = {"campaign_id": str(campaign_id), "workspace_id": str(workspace_id)}
        await record_gauge(
            MetricName.CAMPAIGN_RECIPIENTS_SENT,
            success_count,
            labels=labels,
        )
        await record_gauge(
            MetricName.CAMPAIGN_RECIPIENTS_FAILED,
            failed_count,
            labels=labels,
        )

    @staticmethod
    async def record_campaign_complete(
        campaign_id: int,
        workspace_id: int,
        duration_ms: float,
        success_count: int,
        failed_count: int,
    ) -> None:
        """Record campaign completion."""
        labels = {"campaign_id": str(campaign_id), "workspace_id": str(workspace_id)}
        await record_histogram(
            MetricName.CAMPAIGN_DURATION,
            duration_ms,
            labels=labels,
        )
        await increment_counter(
            MetricName.CAMPAIGN_SENT,
            success_count,
            labels=labels,
        )
        if failed_count > 0:
            await increment_counter(
                MetricName.CAMPAIGN_FAILED,
                failed_count,
                labels=labels,
            )

    @staticmethod
    async def record_campaign_error(
        campaign_id: int,
        workspace_id: int,
        error_type: str,
    ) -> None:
        """Record campaign error."""
        await increment_counter(
            MetricName.CAMPAIGN_FAILED,
            labels={
                "campaign_id": str(campaign_id),
                "workspace_id": str(workspace_id),
                "error_type": error_type,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Message Dispatch Metrics
# ─────────────────────────────────────────────────────────────────────────────

class DispatchMetrics:
    """Metrics for message dispatch."""

    @staticmethod
    async def record_dispatch_start(
        campaign_id: int,
        workspace_id: int,
        phone: str,
    ) -> None:
        """Record dispatch attempt start."""
        await increment_counter(
            "message.dispatch.started",
            labels={"workspace_id": str(workspace_id)},
        )

    @staticmethod
    async def record_dispatch_success(
        campaign_id: int,
        workspace_id: int,
        duration_ms: float,
        provider_message_id: str | None = None,
    ) -> None:
        """Record successful dispatch."""
        await record_histogram(
            MetricName.MESSAGE_DISPATCH_DURATION,
            duration_ms,
            labels={"workspace_id": str(workspace_id), "status": "success"},
        )
        await increment_counter(
            MetricName.MESSAGE_SENT,
            labels={"workspace_id": str(workspace_id), "status": "success"},
        )

    @staticmethod
    async def record_dispatch_failure(
        campaign_id: int,
        workspace_id: int,
        duration_ms: float,
        error_type: str,
        will_retry: bool = True,
    ) -> None:
        """Record failed dispatch."""
        await record_histogram(
            MetricName.MESSAGE_DISPATCH_DURATION,
            duration_ms,
            labels={"workspace_id": str(workspace_id), "status": "failed"},
        )
        await increment_counter(
            MetricName.MESSAGE_FAILED,
            labels={
                "workspace_id": str(workspace_id),
                "error_type": error_type,
                "will_retry": str(will_retry),
            },
        )

    @staticmethod
    async def record_message_delivered(
        campaign_id: int,
        workspace_id: int,
        provider_message_id: str,
    ) -> None:
        """Record message delivery status."""
        await increment_counter(
            MetricName.MESSAGE_DELIVERED,
            labels={"workspace_id": str(workspace_id)},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Recovery System Metrics
# ─────────────────────────────────────────────────────────────────────────────

class RecoveryMetrics:
    """Metrics for campaign recovery."""

    @staticmethod
    async def record_stale_campaign_detected(
        campaign_id: int,
        workspace_id: int,
        stale_duration_seconds: float,
    ) -> None:
        """Record detection of stale campaign."""
        await increment_counter(
            MetricName.RECOVERY_DETECTED,
            labels={"workspace_id": str(workspace_id)},
        )

    @staticmethod
    async def record_recovery_start(
        campaign_id: int,
        workspace_id: int,
    ) -> None:
        """Record recovery start."""
        await increment_counter(
            "recovery.started",
            labels={"workspace_id": str(workspace_id), "campaign_id": str(campaign_id)},
        )

    @staticmethod
    async def record_recovery_complete(
        campaign_id: int,
        workspace_id: int,
        duration_ms: float,
        success: bool = True,
        recipients_resumed: int = 0,
    ) -> None:
        """Record recovery completion."""
        labels = {"workspace_id": str(workspace_id), "campaign_id": str(campaign_id)}
        await record_histogram(
            MetricName.RECOVERY_DURATION,
            duration_ms,
            labels=labels,
        )
        await increment_counter(
            MetricName.RECOVERY_COMPLETED if success else MetricName.RECOVERY_FAILED,
            labels=labels,
        )

    @staticmethod
    async def record_recovery_error(
        campaign_id: int,
        workspace_id: int,
        error_type: str,
    ) -> None:
        """Record recovery error."""
        await increment_counter(
            MetricName.RECOVERY_FAILED,
            labels={
                "workspace_id": str(workspace_id),
                "campaign_id": str(campaign_id),
                "error_type": error_type,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limit Metrics
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitMetrics:
    """Metrics for rate limiting."""

    @staticmethod
    async def record_request_allowed(
        limit_type: str,
        workspace_id: int | None = None,
    ) -> None:
        """Record allowed request."""
        labels = {"limit_type": limit_type}
        if workspace_id:
            labels["workspace_id"] = str(workspace_id)
        await increment_counter(MetricName.RATE_LIMIT_ALLOWED, labels=labels)

    @staticmethod
    async def record_request_rejected(
        limit_type: str,
        workspace_id: int | None = None,
        retry_after_seconds: int | None = None,
    ) -> None:
        """Record rejected request."""
        labels = {"limit_type": limit_type}
        if workspace_id:
            labels["workspace_id"] = str(workspace_id)
        if retry_after_seconds:
            labels["retry_after"] = str(retry_after_seconds)
        await increment_counter(MetricName.RATE_LIMIT_REJECTED, labels=labels)


# ─────────────────────────────────────────────────────────────────────────────
# API Metrics
# ─────────────────────────────────────────────────────────────────────────────

class APIMetrics:
    """Metrics for API requests."""

    @staticmethod
    async def record_request(
        method: str,
        path: str,
        status_code: int,
        duration_ms: float,
        workspace_id: int | None = None,
    ) -> None:
        """Record API request."""
        # Normalize path for metrics (remove IDs)
        normalized_path = _normalize_path(path)

        labels = {
            "method": method,
            "path": normalized_path,
            "status_class": f"{status_code // 100}xx",
        }
        if workspace_id:
            labels["workspace_id"] = str(workspace_id)

        await record_histogram(
            MetricName.API_REQUEST_DURATION,
            duration_ms,
            labels=labels,
        )
        await increment_counter(
            MetricName.API_REQUEST_COUNT,
            labels=labels,
        )

        if status_code >= 400:
            await increment_counter(
                MetricName.API_ERROR_COUNT,
                labels={**labels, "status_code": str(status_code)},
            )

    @staticmethod
    async def record_request_error(
        method: str,
        path: str,
        error_type: str,
        duration_ms: float,
        workspace_id: int | None = None,
    ) -> None:
        """Record API error."""
        normalized_path = _normalize_path(path)

        labels = {
            "method": method,
            "path": normalized_path,
            "error_type": error_type,
        }
        if workspace_id:
            labels["workspace_id"] = str(workspace_id)

        await increment_counter(MetricName.API_ERROR_COUNT, labels=labels)


# ─────────────────────────────────────────────────────────────────────────────
# Redis Metrics
# ─────────────────────────────────────────────────────────────────────────────

class RedisMetrics:
    """Metrics for Redis operations."""

    @staticmethod
    async def record_operation(
        operation: str,
        duration_ms: float,
        success: bool = True,
    ) -> None:
        """Record Redis operation."""
        labels = {"operation": operation, "status": "success" if success else "failed"}
        await record_histogram(
            MetricName.REDIS_OPERATIONS,
            duration_ms,
            labels=labels,
        )

    @staticmethod
    async def record_error(
        operation: str,
        error_type: str,
    ) -> None:
        """Record Redis error."""
        await increment_counter(
            MetricName.REDIS_ERRORS,
            labels={"operation": operation, "error_type": error_type},
        )


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_path(path: str) -> str:
    """Normalize path by replacing IDs with placeholders."""
    import re
    # Replace numeric IDs
    path = re.sub(r'/\d+', '/{id}', path)
    # Replace UUIDs
    path = re.sub(r'/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', '/{uuid}', path, flags=re.IGNORECASE)
    return path


# ─────────────────────────────────────────────────────────────────────────────
# Timing Decorators
# ─────────────────────────────────────────────────────────────────────────────

def timed_operation(name: str, labels: dict[str, str] | None = None):
    """Decorator to time an async operation."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        async def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = await func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                await record_histogram(name, duration_ms, labels)
                return result
            except Exception as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000
                await record_histogram(name, duration_ms, labels)
                raise
        return wrapper
    return decorator


def timed_sync_operation(name: str, labels: dict[str, str] | None = None):
    """Decorator to time a sync operation."""
    def decorator(func: Callable) -> Callable:
        @wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000
                asyncio.create_task(record_histogram(name, duration_ms, labels))
                return result
            except Exception as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000
                asyncio.create_task(record_histogram(name, duration_ms, labels))
                raise
        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Context Managers
# ─────────────────────────────────────────────────────────────────────────────

@contextmanager
def track_duration(
    metric_name: str,
    labels: dict[str, str] | None = None,
):
    """Context manager to track operation duration."""
    start_time = time.perf_counter()
    try:
        yield
    finally:
        duration_ms = (time.perf_counter() - start_time) * 1000
        asyncio.create_task(record_histogram(metric_name, duration_ms, labels))


async def tracked_operation(
    metric_name: str,
    operation: Callable,
    labels: dict[str, str] | None = None,
    *args,
    **kwargs,
):
    """Execute operation and track duration."""
    start_time = time.perf_counter()
    try:
        result = await operation(*args, **kwargs)
        duration_ms = (time.perf_counter() - start_time) * 1000
        await record_histogram(metric_name, duration_ms, labels)
        return result
    except Exception:
        duration_ms = (time.perf_counter() - start_time) * 1000
        await record_histogram(metric_name, duration_ms, labels)
        raise