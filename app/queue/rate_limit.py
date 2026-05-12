"""
Atomic Redis sliding-window rate limits for queue workers and HTTP ingestion edges.

Uses Lua scripts for atomic operations to prevent race conditions under:
- concurrent workers
- parallel campaigns
- webhook spikes
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from redis.asyncio import Redis
from redis.exceptions import RedisError

from app.core.config import get_settings

if TYPE_CHECKING:
    from redis.asyncio import Redis

settings = get_settings()
logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Lua Scripts
# ─────────────────────────────────────────────────────────────────────────────

_SLIDING_WINDOW_SCRIPT = """
-- KEYS[1] = rate limit key
-- ARGV[1] = current timestamp in milliseconds
-- ARGV[2] = window size in milliseconds
-- ARGV[3] = max allowed events
-- ARGV[4] = event id (unique per request)
-- ARGV[5] = TTL for the key in seconds (for cleanup scheduling)

local key = KEYS[1]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local max_events = tonumber(ARGV[3])
local event_id = ARGV[4]
local ttl_seconds = tonumber(ARGV[5])

local window_start = now_ms - window_ms

-- Remove expired entries atomically
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

-- Count current events in window
local current_count = redis.call('ZCARD', key)

if current_count >= max_events then
    -- Rate limit exceeded - return oldest entry timestamp for retry-after calculation
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after_ms = window_ms
    if #oldest > 0 then
        local oldest_ts = tonumber(oldest[2])
        retry_after_ms = (oldest_ts + window_ms) - now_ms
        if retry_after_ms < 1 then
            retry_after_ms = 1
        end
    end
    return {0, current_count, tonumber(retry_after_ms)}
end

-- Under limit - add the event and return success
redis.call('ZADD', key, now_ms, event_id)

-- Schedule key expiry for cleanup (only if not already set)
local current_ttl = redis.call('TTL', key)
if current_ttl == -1 or current_ttl == -2 then
    redis.call('EXPIRE', key, ttl_seconds)
end

-- Return: allowed=1, count after add, retry_after_ms (0 since allowed)
return {1, current_count + 1, 0}
"""

_SLIDING_WINDOW_CLAIM_SCRIPT = """
-- KEYS[1] = rate limit key
-- ARGV[1] = current timestamp in milliseconds
-- ARGV[2] = window size in milliseconds
-- ARGV[3] = max allowed events
-- ARGV[4] = event id (unique per request)
-- ARGV[5] = TTL for the key in seconds
-- ARGV[6] = workspace id for metrics key

local key = KEYS[1]
local metrics_key = 'ratelimit:metrics:' .. ARGV[6]
local now_ms = tonumber(ARGV[1])
local window_ms = tonumber(ARGV[2])
local max_events = tonumber(ARGV[3])
local event_id = ARGV[4]
local ttl_seconds = tonumber(ARGV[5])

local window_start = now_ms - window_ms

-- Remove expired entries
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)

local current_count = redis.call('ZCARD', key)

if current_count >= max_events then
    local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
    local retry_after_ms = window_ms
    if #oldest > 0 then
        local oldest_ts = tonumber(oldest[2])
        retry_after_ms = (oldest_ts + window_ms) - now_ms
        if retry_after_ms < 1 then
            retry_after_ms = 1
        end
    end
    -- Increment rejected counter
    redis.call('HINCRBY', metrics_key, 'rejected', 1)
    redis.call('EXPIRE', metrics_key, 3600)
    return {0, current_count, tonumber(retry_after_ms)}
end

redis.call('ZADD', key, now_ms, event_id)

local current_ttl = redis.call('TTL', key)
if current_ttl == -1 or current_ttl == -2 then
    redis.call('EXPIRE', key, ttl_seconds)
end

-- Increment accepted counter
redis.call('HINCRBY', metrics_key, 'accepted', 1)
redis.call('EXPIRE', metrics_key, 3600)

return {1, current_count + 1, 0}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Exceptions
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitExceeded(Exception):
    """Base exception for rate limit violations."""

    def __init__(self, retry_after_seconds: int, limit_type: str = "unknown"):
        self.retry_after_seconds = retry_after_seconds
        self.limit_type = limit_type
        super().__init__(
            f"{limit_type} rate limit exceeded, retry after {retry_after_seconds}s"
        )


class WebhookIngestRateLimitExceeded(RateLimitExceeded):
    def __init__(self, retry_after_seconds: int):
        super().__init__(
            retry_after_seconds=retry_after_seconds,
            limit_type="webhook_ingest",
        )


class WorkspaceRateLimitExceeded(RateLimitExceeded):
    def __init__(self, retry_after_seconds: int, workspace_id: int):
        self.workspace_id = workspace_id
        super().__init__(
            retry_after_seconds=retry_after_seconds,
            limit_type=f"workspace:{workspace_id}",
        )


# ─────────────────────────────────────────────────────────────────────────────
# Rate Limit Result
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitResultStatus(Enum):
    ALLOWED = "allowed"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class RateLimitResult:
    status: RateLimitResultStatus
    current_count: int
    retry_after_seconds: float
    limit_type: str

    @property
    def allowed(self) -> bool:
        return self.status == RateLimitResultStatus.ALLOWED


@dataclass
class RateLimitMetrics:
    accepted: int = 0
    rejected: int = 0
    errors: int = 0
    last_updated: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "accepted": self.accepted,
            "rejected": self.rejected,
            "errors": self.errors,
            "last_updated": self.last_updated,
        }


# ─────────────────────────────────────────────────────────────────────────────
# Script Registry
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitScriptRegistry:
    """Manages Redis Lua script registration and caching."""

    def __init__(self):
        self._scripts: dict[str, object] = {}
        self._redis: Redis | None = None

    def set_redis(self, redis: Redis) -> None:
        self._redis = redis

    def register(self, name: str, script: str) -> None:
        """Register a Lua script with Redis."""
        if self._redis is None:
            raise RuntimeError("Redis not initialized")
        self._scripts[name] = self._redis.register_script(script)

    def get(self, name: str):
        """Get a registered script."""
        return self._scripts.get(name)

    def load_all(self, redis: Redis) -> None:
        """Load all scripts into Redis."""
        self.set_redis(redis)
        self.register("sliding_window", _SLIDING_WINDOW_SCRIPT)
        self.register("sliding_window_claim", _SLIDING_WINDOW_CLAIM_SCRIPT)


# Global script registry
_scripts = RateLimitScriptRegistry()


async def init_rate_limit_scripts(redis: Redis) -> None:
    """Initialize Lua scripts. Call once at application startup."""
    _scripts.load_all(redis)
    logger.info("Rate limit Lua scripts registered")


# ─────────────────────────────────────────────────────────────────────────────
# Core Atomic Rate Limit Functions
# ─────────────────────────────────────────────────────────────────────────────

async def _atomic_sliding_window(
    redis: Redis,
    key: str,
    max_events: int,
    window_seconds: int,
    event_id: str | None = None,
    record_metrics: bool = False,
    metrics_label: str = "default",
) -> RateLimitResult:
    """
    Atomically enforce sliding-window rate limit using Lua script.

    This single script:
    1. Removes expired entries
    2. Counts remaining entries
    3. Checks if limit exceeded
    4. Adds new entry if allowed
    5. Sets TTL if needed

    All operations are atomic - no race condition between workers.
    """
    if _scripts.get("sliding_window") is None:
        _scripts.load_all(redis)

    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    event_id = event_id or f"{now_ms}-{time.time_ns()}"

    try:
        script = _scripts.get("sliding_window")
        if script is None:
            raise RuntimeError("Sliding window script not registered")

        result = await script(
            keys=[key],
            args=[
                now_ms,
                window_ms,
                max_events,
                event_id,
                window_seconds * 2,  # TTL for key cleanup
            ],
        )

        allowed = bool(result[0])
        current_count = int(result[1])
        retry_after_ms = float(result[2])
        retry_after_seconds = math.ceil(retry_after_ms / 1000)

        if record_metrics:
            metrics_key = f"ratelimit:metrics:{metrics_label}"
            try:
                async with redis.pipeline() as pipe:
                    if allowed:
                        pipe.hincrby(metrics_key, "accepted", 1)
                    else:
                        pipe.hincrby(metrics_key, "rejected", 1)
                    pipe.expire(metrics_key, 3600)
                    await pipe.execute()
            except RedisError as e:
                logger.warning("Failed to update rate limit metrics: %s", e)

        return RateLimitResult(
            status=RateLimitResultStatus.ALLOWED if allowed else RateLimitResultStatus.REJECTED,
            current_count=current_count,
            retry_after_seconds=retry_after_seconds,
            limit_type=metrics_label,
        )

    except RedisError as e:
        logger.error("Redis error in rate limit check: %s", e)
        raise


async def enforce_webhook_ingest_ip_limit(
    redis: Redis,
    client_ip: str,
    limit: int | None = None,
    window_seconds: int = 60,
) -> RateLimitResult:
    """
    Enforce webhook ingest rate limit per IP address.

    Uses atomic Lua script to prevent race conditions when multiple
    webhook deliveries arrive simultaneously.
    """
    limit = limit if limit is not None else settings.webhook_ingest_rate_limit_per_ip_per_minute

    if limit <= 0:
        return RateLimitResult(
            status=RateLimitResultStatus.ALLOWED,
            current_count=0,
            retry_after_seconds=0,
            limit_type=f"webhook_ip:{client_ip}",
        )

    key = f"webhook:ingest:ip:{client_ip}"
    result = await _atomic_sliding_window(
        redis=redis,
        key=key,
        max_events=limit,
        window_seconds=window_seconds,
        record_metrics=True,
        metrics_label=f"webhook_ip:{client_ip}",
    )

    if not result.allowed:
        raise WebhookIngestRateLimitExceeded(
            retry_after_seconds=result.retry_after_seconds
        )

    return result


async def enforce_workspace_rate_limit(
    redis: Redis,
    workspace_id: int,
    max_events: int | None = None,
    window_seconds: int | None = None,
) -> RateLimitResult:
    """
    Enforce workspace rate limit for message sends.

    Uses atomic Lua script to handle concurrent workers processing
    parallel campaigns without race conditions.

    Args:
        redis: Redis client
        workspace_id: Workspace to rate limit
        max_events: Override default limit count
        window_seconds: Override default window duration

    Returns:
        RateLimitResult with allowed/rejected status

    Raises:
        WorkspaceRateLimitExceeded: When limit is exceeded
    """
    max_events = max_events or settings.queue_workspace_rate_limit_count
    window_seconds = window_seconds or settings.queue_workspace_rate_limit_window_seconds

    key = f"queue:rate_limit:{workspace_id}"
    result = await _atomic_sliding_window(
        redis=redis,
        key=key,
        max_events=max_events,
        window_seconds=window_seconds,
        record_metrics=True,
        metrics_label=f"workspace:{workspace_id}",
    )

    if not result.allowed:
        raise WorkspaceRateLimitExceeded(
            retry_after_seconds=result.retry_after_seconds,
            workspace_id=workspace_id,
        )

    return result


async def get_rate_limit_metrics(
    redis: Redis,
    label: str,
) -> RateLimitMetrics:
    """
    Retrieve rate limit metrics for a specific limit type.

    Metrics are stored in a Redis hash and include:
    - accepted: Number of allowed requests
    - rejected: Number of rejected requests
    """
    metrics_key = f"ratelimit:metrics:{label}"

    try:
        data = await redis.hgetall(metrics_key)
        return RateLimitMetrics(
            accepted=int(data.get("accepted", 0)),
            rejected=int(data.get("rejected", 0)),
            errors=int(data.get("errors", 0)),
        )
    except RedisError as e:
        logger.warning("Failed to get rate limit metrics: %s", e)
        return RateLimitMetrics()


async def get_workspace_rate_limit_status(
    redis: Redis,
    workspace_id: int,
    max_events: int | None = None,
    window_seconds: int | None = None,
) -> dict:
    """
    Get current rate limit status for a workspace without consuming a token.

    Useful for monitoring and health checks.
    """
    max_events = max_events or settings.queue_workspace_rate_limit_count
    window_seconds = window_seconds or settings.queue_workspace_rate_limit_window_seconds

    key = f"queue:rate_limit:{workspace_id}"
    now_ms = int(time.time() * 1000)
    window_ms = window_seconds * 1000
    window_start = now_ms - window_ms

    try:
        async with redis.pipeline(transaction=True) as pipe:
            pipe.zremrangebyscore(key, "-inf", window_start)
            pipe.zcard(key)
            pipe.zrange(key, 0, 0, withscores=True)
            results = await pipe.execute()

        current_count = int(results[1])
        oldest = results[2] if len(results) > 2 else []

        retry_after = 0
        if oldest:
            oldest_timestamp = int(oldest[0][1])
            retry_after = max(0, math.ceil((oldest_timestamp + window_ms - now_ms) / 1000))

        return {
            "workspace_id": workspace_id,
            "current_count": current_count,
            "max_events": max_events,
            "window_seconds": window_seconds,
            "limit_remaining": max(0, max_events - current_count),
            "retry_after_seconds": retry_after,
            "within_limit": current_count < max_events,
        }
    except RedisError as e:
        logger.error("Failed to get workspace rate limit status: %s", e)
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Redis Fallback Handling
# ─────────────────────────────────────────────────────────────────────────────

class RateLimitFallbackMode(Enum):
    ALLOW = "allow"  # Allow requests when Redis is down
    DENY = "deny"    # Deny requests when Redis is down


async def enforce_with_fallback(
    redis: Redis,
    rate_limit_func,
    fallback_mode: RateLimitFallbackMode = RateLimitFallbackMode.ALLOW,
    *args,
    **kwargs,
) -> RateLimitResult:
    """
    Execute rate limit with Redis failure fallback.

    When Redis is unavailable:
    - ALLOW mode: Permits requests (fail-open for availability)
    - DENY mode: Rejects requests (fail-closed for safety)
    """
    try:
        return await rate_limit_func(redis, *args, **kwargs)
    except RedisError as e:
        logger.warning("Rate limit Redis error: %s, fallback mode: %s", e, fallback_mode.value)

        if fallback_mode == RateLimitFallbackMode.ALLOW:
            logger.warning("Rate limit fallback: ALLOW (Redis unavailable)")
            return RateLimitResult(
                status=RateLimitResultStatus.ALLOWED,
                current_count=0,
                retry_after_seconds=0,
                limit_type="fallback_allow",
            )
        else:
            logger.warning("Rate limit fallback: DENY (Redis unavailable)")
            raise RateLimitExceeded(
                retry_after_seconds=60,
                limit_type="fallback_deny",
            )
    except Exception as e:
        logger.error("Unexpected error in rate limit: %s", e)
        if fallback_mode == RateLimitFallbackMode.ALLOW:
            return RateLimitResult(
                status=RateLimitResultStatus.ALLOWED,
                current_count=0,
                retry_after_seconds=0,
                limit_type="fallback_error",
            )
        raise


# ─────────────────────────────────────────────────────────────────────────────
# Legacy Compatibility Functions
# ─────────────────────────────────────────────────────────────────────────────

async def enforce_sliding_window_rate_limit(
    redis: Redis,
    *,
    key: str,
    max_events: int,
    window_seconds: int,
) -> None:
    """
    Legacy compatibility function.

    Preserves the original API for existing callers while using
    the new atomic implementation.
    """
    result = await _atomic_sliding_window(
        redis=redis,
        key=key,
        max_events=max_events,
        window_seconds=window_seconds,
    )

    if not result.allowed:
        raise WebhookIngestRateLimitExceeded(
            retry_after_seconds=result.retry_after_seconds
        )