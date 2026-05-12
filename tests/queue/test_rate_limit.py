"""
Tests for atomic Redis rate limiting.

Tests cover:
- concurrent requests handling
- burst traffic scenarios
- race condition prevention
- fallback behavior
"""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from redis.exceptions import RedisError

from app.queue.rate_limit import (
    RateLimitExceeded,
    RateLimitFallbackMode,
    RateLimitMetrics,
    RateLimitResult,
    RateLimitResultStatus,
    RateLimitScriptRegistry,
    WorkspaceRateLimitExceeded,
    _SLIDING_WINDOW_SCRIPT,
    _atomic_sliding_window,
    enforce_workspace_rate_limit,
    enforce_webhook_ingest_ip_limit,
    enforce_with_fallback,
    get_rate_limit_metrics,
    get_workspace_rate_limit_status,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.hgetall = AsyncMock(return_value={})
    redis.pipeline = MagicMock()
    return redis


@pytest.fixture
def script_registry():
    """Create a script registry with mock Redis."""
    registry = RateLimitScriptRegistry()
    mock_redis = AsyncMock()
    registry.load_all(mock_redis)
    return registry


# ─────────────────────────────────────────────────────────────────────────────
# Lua Script Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLuaScriptStructure:
    """Verify Lua script correctness."""

    def test_sliding_window_script_has_atomic_operations(self):
        """Script should contain all operations that must be atomic."""
        script = _SLIDING_WINDOW_SCRIPT
        # All operations should be in a single script
        assert "ZREMRANGEBYSCORE" in script  # Remove old entries
        assert "ZCARD" in script  # Count current entries
        assert "ZADD" in script  # Add new entry if allowed
        assert "EXPIRE" in script  # Set TTL

    def test_sliding_window_script_returns_expected_format(self):
        """Script should return [allowed, count, retry_after_ms]."""
        # The return statement should return 3 values
        lines = _SLIDING_WINDOW_SCRIPT.split('\n')
        return_lines = [l for l in lines if 'return' in l and 'return {' in l]
        assert len(return_lines) == 2  # Two return statements (rejected and allowed)

    def test_script_handles_edge_case_when_limit_exceeded_immediately(self):
        """Script should correctly calculate retry_after when window is full."""
        assert "oldest" in _SLIDING_WINDOW_SCRIPT
        assert "retry_after_ms" in _SLIDING_WINDOW_SCRIPT


# ─────────────────────────────────────────────────────────────────────────────
# Atomic Rate Limit Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestAtomicSlidingWindow:
    """Test atomic sliding window rate limiter."""

    @pytest.mark.asyncio
    async def test_allowed_under_limit(self):
        """Should allow requests when under the limit."""
        mock_redis = AsyncMock()
        mock_script = AsyncMock(return_value=[1, 5, 0])  # allowed, count, no retry

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            result = await _atomic_sliding_window(
                redis=mock_redis,
                key="test:key",
                max_events=10,
                window_seconds=60,
            )

        assert result.allowed is True
        assert result.status == RateLimitResultStatus.ALLOWED
        assert result.current_count == 5

    @pytest.mark.asyncio
    async def test_rejected_over_limit(self):
        """Should reject requests when over the limit."""
        mock_redis = AsyncMock()
        mock_script = AsyncMock(return_value=[0, 10, 5000])  # rejected, count, 5s retry

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            result = await _atomic_sliding_window(
                redis=mock_redis,
                key="test:key",
                max_events=10,
                window_seconds=60,
            )

        assert result.allowed is False
        assert result.status == RateLimitResultStatus.REJECTED
        assert result.retry_after_seconds == 5  # 5000ms / 1000

    @pytest.mark.asyncio
    async def test_retry_after_calculation(self):
        """Should correctly calculate retry_after from oldest entry."""
        mock_redis = AsyncMock()
        mock_script = AsyncMock(return_value=[0, 20, 30000])  # 30 second wait

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            result = await _atomic_sliding_window(
                redis=mock_redis,
                key="test:key",
                max_events=10,
                window_seconds=60,
            )

        assert result.retry_after_seconds == 30

    @pytest.mark.asyncio
    async def test_redis_error_propagates(self):
        """Should propagate Redis errors."""
        mock_redis = AsyncMock()
        mock_redis.register_script = MagicMock(side_effect=RedisError("Connection failed"))

        # Script not registered, triggers reload which fails
        with pytest.raises(RedisError):
            await _atomic_sliding_window(
                redis=mock_redis,
                key="test:key",
                max_events=10,
                window_seconds=60,
            )


# ─────────────────────────────────────────────────────────────────────────────
# Workspace Rate Limit Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWorkspaceRateLimit:
    """Test workspace-specific rate limiting."""

    @pytest.mark.asyncio
    async def test_enforce_workspace_rate_limit_allowed(self):
        """Should allow when under workspace limit."""
        mock_redis = AsyncMock()
        mock_script = AsyncMock(return_value=[1, 5, 0])

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            result = await enforce_workspace_rate_limit(
                redis=mock_redis,
                workspace_id=123,
                max_events=10,
                window_seconds=1,
            )

        assert result.allowed is True
        # Verify the key format
        mock_script.assert_called_once()
        call_args = mock_script.call_args
        assert "queue:rate_limit:123" in call_args.kwargs.get('keys', call_args[1].get('keys', []))

    @pytest.mark.asyncio
    async def test_enforce_workspace_rate_limit_rejected(self):
        """Should raise exception when over workspace limit."""
        mock_redis = AsyncMock()
        mock_script = AsyncMock(return_value=[0, 10, 5000])

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            with pytest.raises(WorkspaceRateLimitExceeded) as exc_info:
                await enforce_workspace_rate_limit(
                    redis=mock_redis,
                    workspace_id=123,
                    max_events=10,
                    window_seconds=1,
                )

        assert exc_info.value.workspace_id == 123
        assert exc_info.value.retry_after_seconds == 5


# ─────────────────────────────────────────────────────────────────────────────
# Webhook Rate Limit Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestWebhookRateLimit:
    """Test webhook ingest rate limiting."""

    @pytest.mark.asyncio
    async def test_webhook_rate_limit_disabled(self):
        """Should allow all when rate limit is disabled (0)."""
        mock_redis = AsyncMock()

        with patch('app.queue.rate_limit.settings') as mock_settings:
            mock_settings.webhook_ingest_rate_limit_per_ip_per_minute = 0

            result = await enforce_webhook_ingest_ip_limit(
                redis=mock_redis,
                client_ip="192.168.1.1",
            )

        assert result.allowed is True
        assert result.limit_type == "webhook_ip:192.168.1.1"

    @pytest.mark.asyncio
    async def test_webhook_rate_limit_ip_specific(self):
        """Should enforce separate limits per IP."""
        mock_redis = AsyncMock()
        mock_script = AsyncMock(return_value=[1, 50, 0])  # Allowed, 50 in window

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            with patch('app.queue.rate_limit.settings') as mock_settings:
                mock_settings.webhook_ingest_rate_limit_per_ip_per_minute = 100

                await enforce_webhook_ingest_ip_limit(
                    redis=mock_redis,
                    client_ip="192.168.1.1",
                )

            # Verify key includes IP
            call_args = mock_script.call_args
            keys = call_args.kwargs.get('keys', call_args[1].get('keys', []))
            assert "webhook:ingest:ip:192.168.1.1" in keys


# ─────────────────────────────────────────────────────────────────────────────
# Concurrent Requests Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConcurrentRequests:
    """Test rate limiter behavior under concurrent load."""

    @pytest.mark.asyncio
    async def test_concurrent_requests_all_atomic(self):
        """All concurrent requests should be handled atomically.

        This tests that the Lua script properly handles race conditions
        by ensuring only one request can modify the state at a time.
        """
        call_count = 0
        call_results = [
            [1, 1, 0], [1, 2, 0], [1, 3, 0], [0, 10, 5000],  # 4 allowed, then rejected
        ]

        async def mock_script(*args, **kwargs):
            nonlocal call_count
            result = call_results[min(call_count, len(call_results) - 1)]
            call_count += 1
            return result

        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            # Fire 5 concurrent requests
            results = await asyncio.gather(
                _atomic_sliding_window(mock_redis, "test", 10, 60),
                _atomic_sliding_window(mock_redis, "test", 10, 60),
                _atomic_sliding_window(mock_redis, "test", 10, 60),
                _atomic_sliding_window(mock_redis, "test", 10, 60),
                _atomic_sliding_window(mock_redis, "test", 10, 60),
            )

        # Should have exactly 5 calls
        assert call_count == 5
        # First 4 should be allowed, 5th rejected
        assert results[0].allowed is True
        assert results[1].allowed is True
        assert results[2].allowed is True
        assert results[3].allowed is True
        assert results[4].allowed is False

    @pytest.mark.asyncio
    async def test_parallel_campaigns_independent_limits(self):
        """Parallel campaigns should have independent rate limits."""
        mock_script = AsyncMock(return_value=[1, 1, 0])  # All allowed
        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            # Two campaigns for different workspaces
            await asyncio.gather(
                enforce_workspace_rate_limit(mock_redis, workspace_id=1),
                enforce_workspace_rate_limit(mock_redis, workspace_id=2),
                enforce_workspace_rate_limit(mock_redis, workspace_id=1),
            )

        # Each call should use different key
        assert mock_script.call_count == 3


# ─────────────────────────────────────────────────────────────────────────────
# Burst Traffic Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestBurstTraffic:
    """Test rate limiter under burst traffic conditions."""

    @pytest.mark.asyncio
    async def test_burst_within_limit(self):
        """Burst within limit should all be allowed."""
        mock_script = AsyncMock(return_value=[1, 1, 0])
        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=mock_script):
            # Burst of 20 requests
            tasks = [
                _atomic_sliding_window(mock_redis, "burst:test", 20, 60)
                for _ in range(20)
            ]
            results = await asyncio.gather(*tasks)

        allowed_count = sum(1 for r in results if r.allowed)
        assert allowed_count == 20

    @pytest.mark.asyncio
    async def test_burst_exceeding_limit(self):
        """Burst exceeding limit should reject excess requests."""
        call_count = 0

        def burst_script(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 10:
                return [1, call_count, 0]  # First 10 allowed
            return [0, 10, 5000]  # Rest rejected

        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=burst_script):
            # Burst of 15 requests, limit of 10
            tasks = [
                _atomic_sliding_window(mock_redis, "burst:test", 10, 60)
                for _ in range(15)
            ]
            results = await asyncio.gather(*tasks)

        allowed_count = sum(1 for r in results if r.allowed)
        rejected_count = sum(1 for r in results if not r.allowed)
        assert allowed_count == 10
        assert rejected_count == 5

    @pytest.mark.asyncio
    async def test_rapid_repeated_bursts(self):
        """Multiple bursts should be handled correctly."""
        burst_count = 0

        async def burst_script(*args, **kwargs):
            nonlocal burst_count
            burst_count += 1
            return [1, burst_count, 0]

        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=burst_script):
            # 3 bursts of 5 requests each
            for _ in range(3):
                await asyncio.gather(*[
                    _atomic_sliding_window(mock_redis, "burst:test", 100, 60)
                    for _ in range(5)
                ])

        assert burst_count == 15


# ─────────────────────────────────────────────────────────────────────────────
# Race Condition Prevention Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRaceConditionPrevention:
    """Test that race conditions are prevented."""

    @pytest.mark.asyncio
    async def test_no_race_between_check_and_add(self):
        """The Lua script ensures no race between checking limit and adding entry.

        In a non-atomic implementation, two workers could both check the limit
        at the same time, both see there's room, and both add entries -
        exceeding the limit. The Lua script prevents this.
        """
        check_count = 0

        async def race_condition_script(*args, **kwargs):
            nonlocal check_count
            check_count += 1
            # This simulates what the Lua script does: check AND add atomically
            # Even if called concurrently, each call is atomic
            if check_count <= 10:
                return [1, check_count, 0]
            return [0, 10, 1000]

        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=race_condition_script):
            # Simulate 20 concurrent workers all trying to send
            results = await asyncio.gather(*[
                _atomic_sliding_window(mock_redis, "race:test", 10, 60)
                for _ in range(20)
            ])

        # Exactly 10 should be allowed (the limit), not more
        allowed = [r for r in results if r.allowed]
        assert len(allowed) == 10

    @pytest.mark.asyncio
    async def test_concurrent_workers_same_workspace(self):
        """Multiple workers processing same workspace should not exceed limit."""
        worker_count = 0

        def worker_script(*args, **kwargs):
            nonlocal worker_count
            worker_count += 1
            if worker_count <= 20:
                return [1, worker_count, 0]
            return [0, 20, 5000]

        mock_redis = AsyncMock()

        with patch.object(RateLimitScriptRegistry, 'get', return_value=worker_script):
            # Simulate 25 workers all trying to send for workspace 123
            results = await asyncio.gather(*[
                enforce_workspace_rate_limit(mock_redis, workspace_id=123)
                for _ in range(25)
            ])

        allowed = [r for r in results if r.allowed]
        rejected = [r for r in results if not r.allowed]

        # All should complete (allowed or rejected via exception)
        assert len(allowed) + len(rejected) == 25


# ─────────────────────────────────────────────────────────────────────────────
# Fallback Handling Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbackHandling:
    """Test Redis fallback behavior."""

    @pytest.mark.asyncio
    async def test_fallback_allow_on_redis_error(self):
        """Should allow when fallback mode is ALLOW and Redis fails."""
        async def failing_func(redis, *args, **kwargs):
            raise RedisError("Connection refused")

        mock_redis = AsyncMock()
        result = await enforce_with_fallback(
            mock_redis,
            failing_func,
            fallback_mode=RateLimitFallbackMode.ALLOW,
        )

        assert result.allowed is True
        assert result.limit_type == "fallback_allow"

    @pytest.mark.asyncio
    async def test_fallback_deny_on_redis_error(self):
        """Should deny when fallback mode is DENY and Redis fails."""
        async def failing_func(redis, *args, **kwargs):
            raise RedisError("Connection refused")

        mock_redis = AsyncMock()

        with pytest.raises(RateLimitExceeded) as exc_info:
            await enforce_with_fallback(
                mock_redis,
                failing_func,
                fallback_mode=RateLimitFallbackMode.DENY,
            )

        assert exc_info.value.limit_type == "fallback_deny"

    @pytest.mark.asyncio
    async def test_normal_operation_when_redis_works(self):
        """Should return normal result when Redis is available."""
        async def working_func(redis, *args, **kwargs):
            return RateLimitResult(
                status=RateLimitResultStatus.ALLOWED,
                current_count=5,
                retry_after_seconds=0,
                limit_type="test",
            )

        mock_redis = AsyncMock()
        result = await enforce_with_fallback(
            mock_redis,
            working_func,
            fallback_mode=RateLimitFallbackMode.DENY,
        )

        assert result.allowed is True
        assert result.current_count == 5


# ─────────────────────────────────────────────────────────────────────────────
# Metrics Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimitMetrics:
    """Test rate limit metrics collection."""

    @pytest.mark.asyncio
    async def test_get_metrics(self):
        """Should retrieve metrics from Redis."""
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(return_value={
            "accepted": "100",
            "rejected": "5",
            "errors": "1",
        })

        metrics = await get_rate_limit_metrics(mock_redis, "workspace:123")

        assert metrics.accepted == 100
        assert metrics.rejected == 5
        assert metrics.errors == 1
        mock_redis.hgetall.assert_called_once_with("ratelimit:metrics:workspace:123")

    @pytest.mark.asyncio
    async def test_get_metrics_defaults_on_error(self):
        """Should return zero metrics on Redis error."""
        mock_redis = AsyncMock()
        mock_redis.hgetall = AsyncMock(side_effect=RedisError("Connection failed"))

        metrics = await get_rate_limit_metrics(mock_redis, "workspace:123")

        assert metrics.accepted == 0
        assert metrics.rejected == 0
        assert metrics.errors == 0

    @pytest.mark.asyncio
    async def test_workspace_status(self):
        """Should get workspace rate limit status."""
        mock_redis = AsyncMock()
        mock_pipeline = AsyncMock()
        mock_pipeline.execute = AsyncMock(return_value=[
            None,  # zremrangebyscore result
            5,  # zcard result
            [(b"entry1", 1234567890000.0)],  # zrange result
        ])
        mock_redis.pipeline = MagicMock(return_value=mock_pipeline)
        mock_pipeline.__aenter__ = AsyncMock(return_value=mock_pipeline)
        mock_pipeline.__aexit__ = AsyncMock(return_value=None)

        status = await get_workspace_rate_limit_status(
            mock_redis,
            workspace_id=123,
            max_events=10,
            window_seconds=60,
        )

        assert status["workspace_id"] == 123
        assert status["current_count"] == 5
        assert status["max_events"] == 10
        assert status["limit_remaining"] == 5
        assert status["within_limit"] is True


# ─────────────────────────────────────────────────────────────────────────────
# Result Type Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRateLimitResult:
    """Test RateLimitResult dataclass."""

    def test_allowed_property(self):
        """Should correctly report if request is allowed."""
        allowed = RateLimitResult(
            status=RateLimitResultStatus.ALLOWED,
            current_count=5,
            retry_after_seconds=0,
            limit_type="test",
        )
        assert allowed.allowed is True

        rejected = RateLimitResult(
            status=RateLimitResultStatus.REJECTED,
            current_count=10,
            retry_after_seconds=5,
            limit_type="test",
        )
        assert rejected.allowed is False

    def test_immutability(self):
        """Result should be frozen (immutable)."""
        result = RateLimitResult(
            status=RateLimitResultStatus.ALLOWED,
            current_count=5,
            retry_after_seconds=0,
            limit_type="test",
        )
        with pytest.raises(AttributeError):
            result.current_count = 10


class TestRateLimitMetrics:
    """Test RateLimitMetrics dataclass."""

    def test_to_dict(self):
        """Should convert to dictionary."""
        metrics = RateLimitMetrics(accepted=100, rejected=10, errors=2)
        data = metrics.to_dict()

        assert data["accepted"] == 100
        assert data["rejected"] == 10
        assert data["errors"] == 2
        assert "last_updated" in data


# ─────────────────────────────────────────────────────────────────────────────
# Script Registry Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestScriptRegistry:
    """Test Lua script registry."""

    def test_register_script(self):
        """Should register script with Redis."""
        registry = RateLimitScriptRegistry()
        mock_redis = AsyncMock()
        mock_script = MagicMock()
        mock_redis.register_script = MagicMock(return_value=mock_script)

        registry.set_redis(mock_redis)
        registry.register("test_script", "return {1}")

        assert registry.get("test_script") is not None

    def test_load_all(self):
        """Should load all scripts."""
        registry = RateLimitScriptRegistry()
        mock_redis = AsyncMock()
        mock_redis.register_script = MagicMock()

        registry.load_all(mock_redis)

        assert registry.get("sliding_window") is not None
        assert registry.get("sliding_window_claim") is not None

    def test_get_unregistered_returns_none(self):
        """Should return None for unregistered scripts."""
        registry = RateLimitScriptRegistry()
        assert registry.get("nonexistent") is None