"""
Centralized metrics collection infrastructure for ChatPulse.

Provides:
- Metrics registry with type-safe counters, histograms, gauges
- Redis-backed temporary metrics cache
- Aggregation service
- OpenTelemetry/Prometheus-ready architecture

Metrics tracked:
- Queue depth
- Task latency
- Webhook latency
- Dispatch latency
- Retry count
- Recovery count
- Worker failures
- API response time
"""

from __future__ import annotations

import asyncio
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import get_settings

if TYPE_CHECKING:
    pass

settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Metric Types
# ─────────────────────────────────────────────────────────────────────────────

class MetricType(str, Enum):
    """Types of metrics."""
    COUNTER = "counter"
    HISTOGRAM = "histogram"
    GAUGE = "gauge"
    TIMER = "timer"


# ─────────────────────────────────────────────────────────────────────────────
# Metric Definitions
# ─────────────────────────────────────────────────────────────────────────────

class MetricName:
    """Canonical metric names."""

    # Queue metrics
    QUEUE_DEPTH = "queue.depth"
    QUEUE_PUBLISHED = "queue.published"
    QUEUE_CONSUMED = "queue.consumed"
    QUEUE_LATENCY = "queue.latency"
    QUEUE_TASK_DURATION = "queue.task.duration"

    # Webhook metrics
    WEBHOOK_RECEIVED = "webhook.received"
    WEBHOOK_PROCESSED = "webhook.processed"
    WEBHOOK_FAILED = "webhook.failed"
    WEBHOOK_LATENCY = "webhook.latency"

    # Campaign metrics
    CAMPAIGN_CREATED = "campaign.created"
    CAMPAIGN_SENT = "campaign.sent"
    CAMPAIGN_FAILED = "campaign.failed"
    CAMPAIGN_DURATION = "campaign.duration"
    CAMPAIGN_RECIPIENTS_TOTAL = "campaign.recipients.total"
    CAMPAIGN_RECIPIENTS_SENT = "campaign.recipients.sent"
    CAMPAIGN_RECIPIENTS_FAILED = "campaign.recipients.failed"

    # Message metrics
    MESSAGE_SENT = "message.sent"
    MESSAGE_DELIVERED = "message.delivered"
    MESSAGE_FAILED = "message.failed"
    MESSAGE_DISPATCH_DURATION = "message.dispatch.duration"

    # API metrics
    API_REQUEST_DURATION = "api.request.duration"
    API_REQUEST_COUNT = "api.request.count"
    API_ERROR_COUNT = "api.error.count"

    # Worker metrics
    WORKER_ACTIVE = "worker.active"
    WORKER_IDLE = "worker.idle"
    WORKER_ERROR = "worker.error"
    WORKER_TASK_DURATION = "worker.task.duration"

    # Recovery metrics
    RECOVERY_DETECTED = "recovery.detected"
    RECOVERY_COMPLETED = "recovery.completed"
    RECOVERY_FAILED = "recovery.failed"
    RECOVERY_DURATION = "recovery.duration"

    # Rate limit metrics
    RATE_LIMIT_ALLOWED = "rate_limit.allowed"
    RATE_LIMIT_REJECTED = "rate_limit.rejected"

    # System metrics
    REDIS_OPERATIONS = "redis.operations"
    REDIS_ERRORS = "redis.errors"


# ─────────────────────────────────────────────────────────────────────────────
# Metric Labels
# ─────────────────────────────────────────────────────────────────────────────

class MetricLabels:
    """Standard label names."""

    WORKSPACE_ID = "workspace_id"
    CAMPAIGN_ID = "campaign_id"
    QUEUE_NAME = "queue_name"
    TASK_NAME = "task_name"
    WORKER_ID = "worker_id"
    STATUS = "status"
    SOURCE = "source"
    ERROR_TYPE = "error_type"
    METHOD = "method"
    PATH = "path"


# ─────────────────────────────────────────────────────────────────────────────
# Metric Value Container
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class MetricValue:
    """Container for a metric value with labels."""
    name: str
    value: float
    metric_type: MetricType
    labels: dict[str, str] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def redis_key(self, prefix: str = "metrics") -> str:
        """Generate Redis key for this metric."""
        label_parts = [
            f"{k}={v}" for k, v in sorted(self.labels.items())
        ]
        label_str = ":".join(label_parts) if label_parts else "default"
        # Truncate to avoid key length issues
        return f"{prefix}:{self.name}:{label_str}"[:200]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "name": self.name,
            "value": self.value,
            "type": self.metric_type.value,
            "labels": self.labels,
            "timestamp": self.timestamp,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Registry
# ─────────────────────────────────────────────────────────────────────────────

class MetricsRegistry:
    """
    Centralized metrics registry.

    Provides type-safe metric collection with:
    - Counters (increment only)
    - Histograms (distribution of values)
    - Gauges (current value)
    - Timers (convenience for histograms)

    Architecture:
    - Metrics are first written to Redis for aggregation
    - Background worker aggregates and flushes to storage
    - Designed to be swapped for Prometheus/OpenTelemetry
    """

    _instance: "MetricsRegistry | None" = None
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    def __init__(self):
        self._redis: redis.Redis | None = None
        self._local_cache: dict[str, float] = {}
        self._histogram_buckets: dict[str, list[float]] = {}
        self._enabled: bool = True
        self._flush_interval: int = 60  # seconds
        self._pending_metrics: list[MetricValue] = []

    @classmethod
    def get_instance(cls) -> "MetricsRegistry":
        """Get singleton instance."""
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def initialize(self, redis_url: str | None = None) -> None:
        """Initialize Redis connection."""
        url = redis_url or settings.redis_url
        self._redis = redis.from_url(url, decode_responses=True)

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.aclose()
            self._redis = None

    def set_enabled(self, enabled: bool) -> None:
        """Enable or disable metrics collection."""
        self._enabled = enabled

    async def increment_counter(
        self,
        name: str,
        value: float = 1.0,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Increment a counter metric.

        Args:
            name: Metric name (e.g., "campaign.sent")
            value: Amount to increment (default 1)
            labels: Optional labels (e.g., {"workspace_id": "123"})
        """
        if not self._enabled:
            return

        metric = MetricValue(
            name=name,
            value=value,
            metric_type=MetricType.COUNTER,
            labels=labels or {},
        )

        await self._record_metric(metric)

    async def record_histogram(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a value in a histogram.

        Args:
            name: Metric name (e.g., "campaign.duration")
            value: Value to record
            labels: Optional labels
        """
        if not self._enabled:
            return

        metric = MetricValue(
            name=name,
            value=value,
            metric_type=MetricType.HISTOGRAM,
            labels=labels or {},
        )

        await self._record_metric(metric)

        # Also track for local percentiles
        key = metric.redis_key()
        if key not in self._histogram_buckets:
            self._histogram_buckets[key] = []
        self._histogram_buckets[key].append(value)
        # Keep only last 1000 values
        if len(self._histogram_buckets[key]) > 1000:
            self._histogram_buckets[key] = self._histogram_buckets[key][-1000:]

    async def record_gauge(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
    ) -> None:
        """
        Record a gauge value.

        Args:
            name: Metric name (e.g., "queue.depth")
            value: Current value
            labels: Optional labels
        """
        if not self._enabled:
            return

        metric = MetricValue(
            name=name,
            value=value,
            metric_type=MetricType.GAUGE,
            labels=labels or {},
        )

        await self._record_metric(metric)

    @contextmanager
    def timing_context(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ):
        """
        Context manager to time an operation and record duration.

        Usage:
            async with metrics.timing_context("campaign.process"):
                await process_campaign()

        Args:
            name: Metric name (will have .duration appended)
            labels: Optional labels
        """
        start_time = time.perf_counter()
        try:
            yield
        finally:
            duration_ms = (time.perf_counter() - start_time) * 1000
            asyncio.create_task(
                self.record_histogram(f"{name}.duration", duration_ms, labels)
            )

    def timing(
        self,
        name: str,
        func: Callable,
        labels: dict[str, str] | None = None,
    ) -> Callable:
        """
        Decorator to time a function.

        Usage:
            @metrics.timing("campaign.process")
            async def process_campaign():
                ...
        """
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                return func(*args, **kwargs)
            finally:
                duration_ms = (time.perf_counter() - start_time) * 1000
                if self._enabled:
                    asyncio.create_task(
                        self.record_histogram(f"{name}.duration", duration_ms, labels)
                    )
        return wrapper

    async def _record_metric(self, metric: MetricValue) -> None:
        """Record metric to Redis."""
        if self._redis is None:
            # Store locally if Redis not available
            self._local_cache[metric.redis_key()] = metric.value
            return

        try:
            await self._redis.zadd(
                f"metrics:raw:{metric.name}",
                {metric.redis_key("metrics:raw"): metric.timestamp},
            )
            await self._redis.hset(
                f"metrics:values:{metric.name}",
                metric.redis_key("metrics:values"),
                metric.value,
            )
            if metric.labels:
                await self._redis.hset(
                    f"metrics:labels:{metric.name}:{metric.redis_key()}",
                    mapping=metric.labels,
                )

            # Track last update time
            await self._redis.zadd(
                "metrics:keys",
                {f"{metric.name}:{metric.redis_key()}": metric.timestamp}
            )

        except RedisError:
            # Fall back to local cache
            key = metric.redis_key()
            if metric.metric_type == MetricType.COUNTER:
                self._local_cache[key] = self._local_cache.get(key, 0) + metric.value
            else:
                self._local_cache[key] = metric.value

    async def flush(self) -> int:
        """Flush pending metrics to storage. Returns count of flushed metrics."""
        if not self._redis:
            return 0

        try:
            # Get all metric keys
            keys = await self._redis.zrange("metrics:keys", 0, -1)
            # Clear keys list
            await self._redis.delete("metrics:keys")

            # Flush local cache
            for key, value in self._local_cache.items():
                await self._redis.hset("metrics:aggregated", key, value)
            self._local_cache.clear()

            return len(keys) if keys else 0

        except RedisError:
            return 0

    async def get_metric(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float | None:
        """Get current value for a metric."""
        if self._redis is None:
            key = MetricValue(name=name, value=0, metric_type=MetricType.GAUGE, labels=labels or {}).redis_key()
            return self._local_cache.get(key)

        try:
            key = MetricValue(name=name, value=0, metric_type=MetricType.GAUGE, labels=labels or {}).redis_key()
            value = await self._redis.hget("metrics:values:" + name, key)
            return float(value) if value else None
        except (RedisError, ValueError):
            return None

    async def get_all_metrics(self) -> dict[str, Any]:
        """Get all current metric values."""
        if self._redis is None:
            return {"local": self._local_cache, "timestamp": time.time()}

        try:
            metrics = await self._redis.hgetall("metrics:values:aggregated")
            result = {}
            for key, value in metrics.items():
                result[key] = float(value)

            return {
                "metrics": result,
                "timestamp": time.time(),
            }
        except RedisError:
            return {"local": self._local_cache, "timestamp": time.time()}


# Global metrics instance
_metrics: MetricsRegistry | None = None


def get_metrics() -> MetricsRegistry:
    """Get or create the global metrics registry."""
    global _metrics
    if _metrics is None:
        _metrics = MetricsRegistry.get_instance()
    return _metrics


async def init_metrics(redis_url: str | None = None) -> None:
    """Initialize metrics registry."""
    metrics = get_metrics()
    await metrics.initialize(redis_url)


# ─────────────────────────────────────────────────────────────────────────────
# Convenience Functions
# ─────────────────────────────────────────────────────────────────────────────

async def increment_counter(
    name: str,
    value: float = 1.0,
    labels: dict[str, str] | None = None,
) -> None:
    """Increment a counter metric."""
    await get_metrics().increment_counter(name, value, labels)


async def record_histogram(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Record a histogram value."""
    await get_metrics().record_histogram(name, value, labels)


async def record_gauge(
    name: str,
    value: float,
    labels: dict[str, str] | None = None,
) -> None:
    """Record a gauge value."""
    await get_metrics().record_gauge(name, value, labels)


@contextmanager
def timing_context(name: str, labels: dict[str, str] | None = None):
    """Time an operation and record duration."""
    metrics = get_metrics()
    with metrics.timing_context(name, labels):
        yield


# ─────────────────────────────────────────────────────────────────────────────
# Export
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Classes
    "MetricsRegistry",
    "MetricValue",
    "MetricType",
    # Enums
    "MetricName",
    "MetricLabels",
    # Functions
    "get_metrics",
    "init_metrics",
    "increment_counter",
    "record_histogram",
    "record_gauge",
    "timing_context",
]