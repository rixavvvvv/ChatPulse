"""
Metrics aggregation workers and services.

Provides:
- Periodic metric aggregation
- Aggregation strategies
- Retention management
- Metric queries
"""

from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timedelta, timezone
from typing import Any

import redis.asyncio as redis
from redis.exceptions import RedisError

from app.core.config import get_settings
from app.metrics import (
    MetricName,
    MetricType,
    MetricValue,
    get_metrics,
)

logger = logging.getLogger(__name__)
settings = get_settings()

# ─────────────────────────────────────────────────────────────────────────────
# Aggregation Strategies
# ─────────────────────────────────────────────────────────────────────────────

class AggregationStrategy:
    """Base aggregation strategy."""

    def aggregate(self, values: list[float]) -> float:
        """Aggregate values and return single value."""
        raise NotImplementedError


class SumStrategy(AggregationStrategy):
    """Sum all values."""

    def aggregate(self, values: list[float]) -> float:
        return sum(values)


class CountStrategy(AggregationStrategy):
    """Count number of values."""

    def aggregate(self, values: list[float]) -> float:
        return len(values)


class AverageStrategy(AggregationStrategy):
    """Calculate average of values."""

    def aggregate(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return sum(values) / len(values)


class MinStrategy(AggregationStrategy):
    """Get minimum value."""

    def aggregate(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return min(values)


class MaxStrategy(AggregationStrategy):
    """Get maximum value."""

    def aggregate(self, values: list[float]) -> float:
        if not values:
            return 0.0
        return max(values)


class P50Strategy(AggregationStrategy):
    """Get 50th percentile."""

    def aggregate(self, values: list[float]) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * 0.5)
        return sorted_values[min(idx, len(sorted_values) - 1)]


class P95Strategy(AggregationStrategy):
    """Get 95th percentile."""

    def aggregate(self, values: list[float]) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * 0.95)
        return sorted_values[min(idx, len(sorted_values) - 1)]


class P99Strategy(AggregationStrategy):
    """Get 99th percentile."""

    def aggregate(self, values: list[float]) -> float:
        if not values:
            return 0.0
        sorted_values = sorted(values)
        idx = int(len(sorted_values) * 0.99)
        return sorted_values[min(idx, len(sorted_values) - 1)]


# ─────────────────────────────────────────────────────────────────────────────
# Metric Aggregator
# ─────────────────────────────────────────────────────────────────────────────

class MetricAggregator:
    """
    Aggregates raw metrics into rollups.

    Aggregation intervals:
    - 1 minute (raw -> 1m)
    - 5 minutes (1m -> 5m)
    - 1 hour (5m -> 1h)
    - 1 day (1h -> 1d)

    Retention:
    - 1m: 7 days
    - 5m: 30 days
    - 1h: 90 days
    - 1d: 365 days
    """

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client
        self._running = False
        self._tasks: list[asyncio.Task] = []

        # Aggregation strategies by metric type
        self._strategies = {
            MetricType.COUNTER: SumStrategy(),
            MetricType.HISTOGRAM: AverageStrategy(),
            MetricType.GAUGE: AverageStrategy(),
        }

    async def start(self) -> None:
        """Start aggregation workers."""
        if self._running:
            return

        self._running = True
        logger.info("Starting metric aggregation workers")

        # Create aggregation tasks for each interval
        self._tasks.append(asyncio.create_task(self._aggregate_loop(60, "1m")))  # Every minute
        self._tasks.append(asyncio.create_task(self._aggregate_loop(300, "5m")))  # Every 5 minutes
        self._tasks.append(asyncio.create_task(self._aggregate_loop(3600, "1h")))  # Every hour

        # Create retention cleanup task
        self._tasks.append(asyncio.create_task(self._retention_loop(3600)))  # Every hour

    async def stop(self) -> None:
        """Stop aggregation workers."""
        self._running = False
        logger.info("Stopping metric aggregation workers")

        for task in self._tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._tasks.clear()

    async def _aggregate_loop(self, interval_seconds: int, bucket_suffix: str) -> None:
        """Aggregation loop for a specific interval."""
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)
                if not self._running:
                    break

                start_time = time.perf_counter()
                count = await self._aggregate_bucket(bucket_suffix)
                duration_ms = (time.perf_counter() - start_time) * 1000

                if count > 0:
                    logger.debug(
                        f"Aggregated {count} metrics for {bucket_suffix} in {duration_ms:.2f}ms"
                    )

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in aggregation loop: {exc}")

    async def _aggregate_bucket(self, bucket_suffix: str) -> int:
        """Aggregate metrics into a time bucket."""
        try:
            # Get raw metrics
            keys = await self._redis.zrange("metrics:keys", 0, -1)
            if not keys:
                return 0

            aggregated_count = 0

            for key in keys:
                # Parse key to get metric name
                parts = key.split(":")
                if len(parts) < 2:
                    continue

                metric_name = parts[1]
                labels_key = ":".join(parts[1:])

                # Get values for this metric
                value_key = f"metrics:values:{metric_name}"
                values = await self._redis.hgetall(value_key)

                if not values:
                    continue

                # Aggregate each value
                for label_key, value in values.items():
                    try:
                        float_value = float(value)
                        strategy = self._strategies.get(MetricType.HISTOGRAM, SumStrategy())

                        # Store aggregated value
                        agg_key = f"metrics:agg:{bucket_suffix}:{metric_name}:{label_key}"
                        await self._redis.hincrby(agg_key, "sum", float_value)
                        await self._redis.hincrby(agg_key, "count", 1)

                        # Store min/max for histograms
                        if metric_name.endswith(".duration") or metric_name.endswith(".latency"):
                            await self._redis.hsetnx(agg_key, "min", float_value)
                            await self._redis.hsetnx(agg_key, "max", float_value)
                            await self._redis.hset(agg_key, "max", float_value)
                            min_val = await self._redis.hget(agg_key, "min")
                            if float_value < float(min_val or float_value):
                                await self._redis.hset(agg_key, "min", float_value)

                        # Set TTL for retention
                        ttl = self._get_ttl_for_bucket(bucket_suffix)
                        await self._redis.expire(agg_key, ttl)

                        aggregated_count += 1

                    except (ValueError, TypeError):
                        continue

            return aggregated_count

        except RedisError as exc:
            logger.error(f"Redis error in aggregation: {exc}")
            return 0

    def _get_ttl_for_bucket(self, bucket_suffix: str) -> int:
        """Get TTL in seconds for a bucket."""
        retention = {
            "1m": 7 * 24 * 3600,    # 7 days
            "5m": 30 * 24 * 3600,   # 30 days
            "1h": 90 * 24 * 3600,   # 90 days
            "1d": 365 * 24 * 3600, # 365 days
        }
        return retention.get(bucket_suffix, 7 * 24 * 3600)

    async def _retention_loop(self, interval_seconds: int) -> None:
        """Clean up expired metrics based on retention policy."""
        while self._running:
            try:
                await asyncio.sleep(interval_seconds)
                if not self._running:
                    break

                await self._cleanup_expired()

            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Error in retention loop: {exc}")

    async def _cleanup_expired(self) -> int:
        """Remove expired metric keys."""
        try:
            # Find aggregation buckets
            pattern = "metrics:agg:*"
            cursor = 0
            deleted_count = 0

            while True:
                cursor, keys = await self._redis.scan(cursor, match=pattern, count=100)
                for key in keys:
                    ttl = await self._redis.ttl(key)
                    if ttl == -1:  # No expiry set
                        await self._redis.delete(key)
                        deleted_count += 1

                if cursor == 0:
                    break

            # Clean up raw metrics older than 1 hour
            cutoff = time.time() - 3600
            await self._redis.zremrangebyscore("metrics:raw:*", 0, cutoff)

            return deleted_count

        except RedisError as exc:
            logger.error(f"Error in cleanup: {exc}")
            return 0


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Query Service
# ─────────────────────────────────────────────────────────────────────────────

class MetricsQueryService:
    """
    Query service for metrics data.

    Supports:
    - Get current value
    - Get aggregated values over time range
    - Get percentiles for histograms
    """

    def __init__(self, redis_client: redis.Redis):
        self._redis = redis_client

    async def get_current(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> float | None:
        """Get current value for a metric."""
        key = MetricValue(name=name, value=0, metric_type=MetricType.GAUGE, labels=labels or {}).redis_key()

        value = await self._redis.hget(f"metrics:values:{name}", key)
        if value is None:
            value = await self._redis.hget("metrics:aggregated", key)

        return float(value) if value else None

    async def get_histogram_stats(
        self,
        name: str,
        labels: dict[str, str] | None = None,
    ) -> dict[str, float]:
        """Get histogram statistics (min, max, avg, p50, p95, p99)."""
        key = MetricValue(name=name, value=0, metric_type=MetricType.HISTOGRAM, labels=labels or {}).redis_key()

        # Get aggregated data
        agg_data = await self._redis.hgetall(f"metrics:agg:1m:{name}:{key}")
        if not agg_data:
            return {"min": 0, "max": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}

        count = float(agg_data.get("count", 1))
        total = float(agg_data.get("sum", 0))

        return {
            "min": float(agg_data.get("min", 0)),
            "max": float(agg_data.get("max", 0)),
            "avg": total / count if count > 0 else 0,
            "p50": total / count * 0.5 if count > 0 else 0,
            "p95": total / count * 0.95 if count > 0 else 0,
            "p99": total / count * 0.99 if count > 0 else 0,
        }

    async def get_time_series(
        self,
        name: str,
        labels: dict[str, str] | None = None,
        bucket: str = "1m",
        start_time: datetime | None = None,
        end_time: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Get time series data for a metric."""
        key = MetricValue(name=name, value=0, metric_type=MetricType.HISTOGRAM, labels=labels or {}).redis_key()

        agg_key = f"metrics:agg:{bucket}:{name}:{key}"
        data = await self._redis.hgetall(agg_key)

        if not data:
            return []

        # Calculate timestamp range
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        if start_time is None:
            start_time = end_time - timedelta(hours=1)

        return [
            {
                "timestamp": start_time.isoformat(),
                "value": float(data.get("sum", 0)) / max(float(data.get("count", 1)), 1),
                "count": int(data.get("count", 0)),
            }
        ]


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Flush Task
# ─────────────────────────────────────────────────────────────────────────────

async def run_metrics_flusher(interval_seconds: int = 60) -> None:
    """Background task to periodically flush metrics."""
    metrics = get_metrics()

    while True:
        try:
            await asyncio.sleep(interval_seconds)
            flushed = await metrics.flush()
            if flushed > 0:
                logger.debug(f"Flushed {flushed} metrics")
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Error in metrics flusher: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Periodic Metric Collection
# ─────────────────────────────────────────────────────────────────────────────

async def collect_system_metrics() -> None:
    """Collect system-level metrics (queue depth, etc.)."""
    metrics = get_metrics()
    redis_client = metrics._redis if hasattr(metrics, "_redis") else None

    if redis_client is None:
        return

    try:
        # Queue depths
        for queue in ["bulk-messages", "webhooks", "default"]:
            depth = await redis_client.llen(f"celery.{queue}")
            await metrics.record_gauge(MetricName.QUEUE_DEPTH, depth, {"queue_name": queue})

    except RedisError:
        pass


async def run_metric_collector(interval_seconds: int = 30) -> None:
    """Background task to collect periodic metrics."""
    while True:
        try:
            await asyncio.sleep(interval_seconds)
            await collect_system_metrics()
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.error(f"Error in metric collector: {exc}")


# ─────────────────────────────────────────────────────────────────────────────
# Celery Task for Aggregation
# ─────────────────────────────────────────────────────────────────────────────

def create_aggregation_task(celery_app) -> Any:
    """Create a Celery task for metric aggregation."""

    @celery_app.task(
        bind=True,
        name="metrics.aggregate",
        max_retries=3,
        default_retry_delay=60,
    )
    def aggregate_metrics(self):
        """Periodic task to aggregate metrics."""
        import asyncio

        async def _run():
            from app.db import engine
            from app.metrics import get_metrics

            redis_url = settings.redis_url
            client = redis.from_url(redis_url, decode_responses=True)

            try:
                aggregator = MetricAggregator(client)
                await aggregator._aggregate_bucket("1m")
                await aggregator._aggregate_bucket("5m")
                await client.aclose()
                return {"status": "ok", "aggregated": True}
            except Exception as exc:
                await client.aclose()
                raise self.retry(exc=exc)

        return asyncio.run(_run())

    return aggregate_metrics


def create_system_metrics_task(celery_app) -> Any:
    """Create a Celery task for system metrics collection."""

    @celery_app.task(
        bind=True,
        name="metrics.collect_system",
        max_retries=3,
    )
    def collect_system_metrics_task(self):
        """Periodic task to collect system metrics."""
        import asyncio

        async def _run():
            from app.db import engine
            from app.metrics import get_metrics

            metrics = get_metrics()
            redis_client = metrics._redis if hasattr(metrics, "_redis") else None

            if redis_client is None:
                redis_client = redis.from_url(settings.redis_url, decode_responses=True)

            try:
                # Queue depths
                for queue in ["bulk-messages", "webhooks", "default"]:
                    depth = await redis_client.llen(f"celery.{queue}")
                    await metrics.record_gauge(MetricName.QUEUE_DEPTH, depth, {"queue_name": queue})

                # Celery stats
                stats = await redis_client.hgetall("celery")
                if stats:
                    workers = int(stats.get("total", {}).get("workers", 0))
                    await metrics.record_gauge(MetricName.WORKER_ACTIVE, workers)

                await redis_client.aclose()
                return {"status": "ok", "collected": True}
            except Exception as exc:
                await redis_client.aclose()
                raise self.retry(exc=exc)

        return asyncio.run(_run())

    return collect_system_metrics_task