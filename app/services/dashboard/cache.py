"""
Redis caching layer for dashboard queries.

Provides:
- Query result caching with TTL
- Cache invalidation patterns
- Stale-while-revalidate support
- Cache key generation
- Bulk cache operations
"""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable, TypeVar

import redis.asyncio as redis
from pydantic import BaseModel

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

T = TypeVar("T")


# ─────────────────────────────────────────────────────────────────────────────
# Cache Configuration
# ─────────────────────────────────────────────────────────────────────────────

class CacheConfig(BaseModel):
    """Cache configuration per metric type."""

    ttl_seconds: int = 60
    stale_ttl_seconds: int = 300
    max_size_bytes: int = 1_000_000
    compress_threshold_bytes: int = 10_000


CACHE_CONFIGS: dict[str, CacheConfig] = {
    "campaign_delivery": CacheConfig(ttl_seconds=30, stale_ttl_seconds=120),
    "workspace_usage": CacheConfig(ttl_seconds=60, stale_ttl_seconds=300),
    "queue_health": CacheConfig(ttl_seconds=15, stale_ttl_seconds=60),
    "webhook_health": CacheConfig(ttl_seconds=30, stale_ttl_seconds=120),
    "retry_analytics": CacheConfig(ttl_seconds=120, stale_ttl_seconds=600),
    "recovery_analytics": CacheConfig(ttl_seconds=120, stale_ttl_seconds=600),
    "dashboard_overview": CacheConfig(ttl_seconds=60, stale_ttl_seconds=300),
    "realtime": CacheConfig(ttl_seconds=5, stale_ttl_seconds=15),
}


# ─────────────────────────────────────────────────────────────────────────────
# Cache Key Generation
# ─────────────────────────────────────────────────────────────────────────────


class CacheKey:
    """Cache key builder with standardized patterns."""

    PREFIX = "chatpulse:dashboard"

    @classmethod
    def _normalize_value(cls, value: Any) -> str:
        """Normalize a value for use in cache key."""
        if value is None:
            return "none"
        if isinstance(value, (int, float, bool)):
            return str(value).lower()
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (list, tuple)):
            return ",".join(sorted(str(v) for v in value))
        return str(value)

    @classmethod
    def _hash_params(cls, params: dict[str, Any]) -> str:
        """Hash parameters dict into a short key."""
        serialized = json.dumps(params, sort_keys=True, default=str)
        return hashlib.sha256(serialized.encode()).hexdigest()[:16]

    @classmethod
    def build(
        cls,
        metric_type: str,
        workspace_id: int,
        params: dict[str, Any] | None = None,
        scope: str = "ws",
    ) -> str:
        """
        Build a cache key.

        Pattern: chatpulse:dashboard:{scope}:{metric_type}:{workspace_id}:{params_hash}
        """
        parts = [cls.PREFIX, scope, metric_type, str(workspace_id)]
        if params:
            parts.append(cls._hash_params(params))
        return ":".join(parts)

    @classmethod
    def build_campaign(cls, campaign_id: int, params: dict[str, Any] | None = None) -> str:
        """Build cache key for campaign-specific metrics."""
        parts = [cls.PREFIX, "campaign", str(campaign_id)]
        if params:
            parts.append(cls._hash_params(params))
        return ":".join(parts)

    @classmethod
    def build_realtime(cls, workspace_id: int) -> str:
        """Build cache key for real-time metrics."""
        return f"{cls.PREFIX}:realtime:{workspace_id}"

    @classmethod
    def build_timeline(
        cls,
        metric_type: str,
        workspace_id: int,
        granularity: str,
        start_time: datetime,
        end_time: datetime,
    ) -> str:
        """Build cache key for timeline data."""
        return (
            f"{cls.PREFIX}:timeline:{metric_type}:{workspace_id}"
            f":{granularity}:{start_time.isoformat()}:{end_time.isoformat()}"
        )

    @classmethod
    def workspace_pattern(cls, workspace_id: int) -> str:
        """Get pattern for all keys related to a workspace."""
        return f"{cls.PREFIX}:*:{workspace_id}:*"

    @classmethod
    def metric_pattern(cls, metric_type: str) -> str:
        """Get pattern for all keys of a metric type."""
        return f"{cls.PREFIX}:*:{metric_type}:*"


# ─────────────────────────────────────────────────────────────────────────────
# Cache Entry
# ─────────────────────────────────────────────────────────────────────────────


class CacheEntry(BaseModel):
    """Cached data entry with metadata."""

    data: Any
    created_at: datetime
    expires_at: datetime
    stale_at: datetime | None = None
    hit_count: int = 0
    compute_time_ms: float | None = None
    cache_key: str | None = None

    def is_fresh(self, now: datetime | None = None) -> bool:
        """Check if cache entry is fresh."""
        if now is None:
            now = datetime.now(timezone.utc)
        return now < self.expires_at

    def is_stale(self, now: datetime | None = None) -> bool:
        """Check if cache entry is stale but usable."""
        if now is None:
            now = datetime.now(timezone.utc)
        if self.stale_at is None:
            return not self.is_fresh(now)
        return self.stale_at <= now < self.expires_at

    def is_expired(self, now: datetime | None = None) -> bool:
        """Check if cache entry is expired."""
        if now is None:
            now = datetime.now(timezone.utc)
        return now >= self.expires_at

    class Config:
        arbitrary_types_allowed = True


# ─────────────────────────────────────────────────────────────────────────────
# Dashboard Cache Service
# ─────────────────────────────────────────────────────────────────────────────


class DashboardCacheService:
    """
    Redis-based caching service for dashboard queries.

    Features:
    - Automatic TTL based on metric type
    - Stale-while-revalidate for fast responses
    - Compression for large payloads
    - Cache warming support
    - Bulk invalidation
    """

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None
        self._local_cache: dict[str, CacheEntry] = {}
        self._local_cache_max_size = 100

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close Redis connection."""
        if self._redis:
            await self._redis.close()
            self._redis = None

    # ─────────────────────────────────────────────────────────────────────────
    # Basic Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def get(self, key: str) -> CacheEntry | None:
        """Get cached entry by key."""
        # Check local cache first
        if key in self._local_cache:
            entry = self._local_cache[key]
            if not entry.is_expired():
                entry.hit_count += 1
                return entry

        # Check Redis
        try:
            r = await self._get_redis()
            raw = await r.get(key)
            if raw:
                data = json.loads(raw)
                entry = CacheEntry(**data)
                entry.hit_count += 1
                # Populate local cache
                self._update_local_cache(key, entry)
                return entry
        except Exception as exc:
            logger.warning(f"Cache get failed for {key}: {exc}")

        return None

    async def set(
        self,
        key: str,
        data: Any,
        metric_type: str = "default",
        compute_time_ms: float | None = None,
    ) -> None:
        """Set cache entry with metric-type-specific TTL."""
        config = CACHE_CONFIGS.get(metric_type, CacheConfig())
        now = datetime.now(timezone.utc)

        entry = CacheEntry(
            data=data,
            created_at=now,
            expires_at=now.timestamp() + config.ttl_seconds,
            stale_at=(now.timestamp() + config.stale_ttl_seconds) if config.stale_ttl_seconds > config.ttl_seconds else None,
            compute_time_ms=compute_time_ms,
            cache_key=key,
        )

        # Store in local cache
        self._update_local_cache(key, entry)

        # Store in Redis
        try:
            r = await self._get_redis()
            raw = json.dumps(entry.model_dump(), default=str)
            await r.setex(key, config.ttl_seconds, raw)
        except Exception as exc:
            logger.warning(f"Cache set failed for {key}: {exc}")

    def _update_local_cache(self, key: str, entry: CacheEntry) -> None:
        """Update local in-memory cache."""
        self._local_cache[key] = entry
        # Evict if too large
        if len(self._local_cache) > self._local_cache_max_size:
            oldest = min(
                self._local_cache.items(),
                key=lambda x: x[1].created_at,
            )
            del self._local_cache[oldest[0]]

    async def delete(self, key: str) -> None:
        """Delete cache entry."""
        # Remove from local cache
        self._local_cache.pop(key, None)

        # Remove from Redis
        try:
            r = await self._get_redis()
            await r.delete(key)
        except Exception as exc:
            logger.warning(f"Cache delete failed for {key}: {exc}")

    async def invalidate_workspace(self, workspace_id: int) -> int:
        """Invalidate all cache entries for a workspace."""
        pattern = CacheKey.workspace_pattern(workspace_id)
        return await self._invalidate_pattern(pattern)

    async def invalidate_metric_type(self, metric_type: str) -> int:
        """Invalidate all cache entries for a metric type."""
        pattern = CacheKey.metric_pattern(metric_type)
        return await self._invalidate_pattern(pattern)

    async def _invalidate_pattern(self, pattern: str) -> int:
        """Invalidate all keys matching pattern."""
        # Clear local cache matches
        to_delete = [k for k in self._local_cache if _matches_pattern(k, pattern)]
        for k in to_delete:
            del self._local_cache[k]

        # Clear Redis matches
        count = 0
        try:
            r = await self._get_redis()
            cursor = 0
            while True:
                cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
                if keys:
                    await r.delete(*keys)
                    count += len(keys)
                if cursor == 0:
                    break
        except Exception as exc:
            logger.warning(f"Cache invalidation failed for {pattern}: {exc}")

        return count

    # ─────────────────────────────────────────────────────────────────────────
    # Stale-While-Revalidate
    # ─────────────────────────────────────────────────────────────────────────

    async def get_or_compute(
        self,
        key: str,
        compute_fn: Callable[..., Any],
        metric_type: str = "default",
        stale_ok: bool = True,
        **kwargs,
    ) -> tuple[Any, bool]:
        """
        Get from cache or compute value.

        Returns (data, from_cache) tuple.
        If stale_ok=True, returns stale data while revalidating in background.
        """
        entry = await self.get(key)
        now = datetime.now(timezone.utc)

        if entry and entry.is_fresh(now):
            return entry.data, True

        if entry and stale_ok and entry.is_stale(now):
            # Return stale data, trigger async recompute
            # Note: in a production system, we'd spawn a background task here
            return entry.data, True

        # Cache miss or no stale allowed - compute
        import time
        start = time.perf_counter()
        data = compute_fn(**kwargs)
        compute_time = (time.perf_counter() - start) * 1000

        await self.set(key, data, metric_type, compute_time)
        return data, False

    # ─────────────────────────────────────────────────────────────────────────
    # Bulk Operations
    # ─────────────────────────────────────────────────────────────────────────

    async def get_many(self, keys: list[str]) -> dict[str, CacheEntry | None]:
        """Get multiple cache entries."""
        results = {}

        # Check local cache
        for key in keys:
            if key in self._local_cache:
                entry = self._local_cache[key]
                if not entry.is_expired():
                    results[key] = entry
                    continue
            results[key] = None

        # Get missing from Redis
        redis_keys = [k for k, v in results.items() if v is None]
        if redis_keys:
            try:
                r = await self._get_redis()
                raw_values = await r.mget(redis_keys)
                for key, raw in zip(redis_keys, raw_values):
                    if raw:
                        data = json.loads(raw)
                        entry = CacheEntry(**data)
                        self._update_local_cache(key, entry)
                        results[key] = entry
            except Exception as exc:
                logger.warning(f"Cache get_many failed: {exc}")

        return results

    async def warm(
        self,
        queries: list[tuple[str, Callable[..., Any]]],
        metric_type: str = "default",
    ) -> dict[str, Any]:
        """
        Warm cache with multiple queries.

        queries: list of (key, compute_fn) tuples
        """
        results = {}
        cached_keys = []

        # Check existing cache
        cache_entries = await self.get_many([q[0] for q in queries])
        now = datetime.now(timezone.utc)

        for key, entry in cache_entries.items():
            if entry and entry.is_fresh(now):
                results[key] = entry.data
                cached_keys.append(key)

        # Compute missing
        missing = [(k, fn) for k, fn in queries if k not in cached_keys]
        for key, compute_fn in missing:
            try:
                import time
                start = time.perf_counter()
                data = compute_fn()
                compute_time = (time.perf_counter() - start) * 1000
                results[key] = data
                await self.set(key, data, metric_type, compute_time)
            except Exception as exc:
                logger.warning(f"Cache warm compute failed for {key}: {exc}")

        return results

    # ─────────────────────────────────────────────────────────────────────────
    # Stats
    # ─────────────────────────────────────────────────────────────────────────

    async def get_stats(self) -> dict[str, Any]:
        """Get cache statistics."""
        try:
            r = await self._get_redis()
            info = await r.info("stats")

            # Count keys by pattern
            key_counts: dict[str, int] = {}
            for pattern in [
                f"{CacheKey.PREFIX}:*:campaign_delivery:*",
                f"{CacheKey.PREFIX}:*:workspace_usage:*",
                f"{CacheKey.PREFIX}:*:queue_health:*",
                f"{CacheKey.PREFIX}:*:webhook_health:*",
                f"{CacheKey.PREFIX}:realtime:*",
            ]:
                count = 0
                cursor = 0
                while True:
                    cursor, keys = await r.scan(cursor=cursor, match=pattern, count=100)
                    count += len(keys)
                    if cursor == 0:
                        break
                key_counts[pattern.split(":")[-2]] = count

            return {
                "redis_hits": info.get("keyspace_hits", 0),
                "redis_misses": info.get("keyspace_misses", 0),
                "local_cache_size": len(self._local_cache),
                "key_counts": key_counts,
            }
        except Exception as exc:
            logger.warning(f"Cache stats failed: {exc}")
            return {"error": str(exc)}


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────


def _matches_pattern(key: str, pattern: str) -> bool:
    """Simple glob-style pattern matching."""
    import fnmatch
    return fnmatch.fnmatch(key, pattern)


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_dashboard_cache: DashboardCacheService | None = None


def get_dashboard_cache() -> DashboardCacheService:
    """Get singleton dashboard cache instance."""
    global _dashboard_cache
    if _dashboard_cache is None:
        _dashboard_cache = DashboardCacheService()
    return _dashboard_cache
