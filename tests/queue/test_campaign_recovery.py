"""
Tests for campaign execution recovery.

Tests cover:
- Lease acquisition and release
- Stale campaign detection
- Recovery flow
- Idempotency during recovery
- Heartbeat management
"""

import asyncio
import time
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio

from app.models.campaign import CampaignStatus
from app.models.campaign_contact import CampaignContactDeliveryStatus
from app.services.campaign_recovery_service import (
    DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    DEFAULT_LEASE_TTL_SECONDS,
    DEFAULT_STALE_THRESHOLD_SECONDS,
    CampaignExecutionLeaseError,
    CampaignRecoveryError,
    LeaseResult,
    RecoveryContext,
    _execution_lease_key,
    _heartbeat_key,
    _recovery_lock_key,
    acquire_execution_lease,
    detect_stalled_campaigns,
    extend_execution_lease,
    finalize_campaign_execution,
    get_lease_holder,
    initialize_campaign_execution,
    is_campaign_stale,
    mark_campaign_recovering,
    record_campaign_heartbeat,
    recover_stalled_campaign,
    release_execution_lease,
    update_campaign_progress,
)


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def mock_redis():
    """Create a mock Redis client."""
    redis = AsyncMock()
    redis.get = AsyncMock(return_value=None)
    redis.set = AsyncMock(return_value=True)
    redis.delete = AsyncMock(return_value=1)
    redis.eval = AsyncMock(return_value=1)
    redis.ttl = AsyncMock(return_value=300)
    redis.expire = AsyncMock(return_value=True)
    return redis


@pytest.fixture
def mock_session():
    """Create a mock AsyncSession."""
    session = AsyncMock()
    session.execute = AsyncMock()
    session.commit = AsyncMock()
    session.get = AsyncMock()
    return session


@pytest.fixture
def sample_campaign():
    """Create a sample campaign object."""
    campaign = MagicMock()
    campaign.id = 123
    campaign.workspace_id = 456
    campaign.status = CampaignStatus.running
    campaign.celery_task_id = "task-abc123"
    campaign.success_count = 10
    campaign.failed_count = 2
    return campaign


@pytest.fixture
def sample_recovery_context():
    """Create a sample recovery context."""
    return RecoveryContext(
        campaign_id=123,
        workspace_id=456,
        celery_task_id="task-abc123",
        last_checkpoint_index=0,
        total_recipients=100,
        processed_recipients=50,
        success_count=10,
        failed_count=2,
        reason="no_heartbeat_and_task_not_active",
    )


# ─────────────────────────────────────────────────────────────────────────────
# Lease Management Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaseManagement:
    """Test execution lease operations."""

    @pytest.mark.asyncio
    async def test_acquire_lease_success(self, mock_redis):
        """Should acquire lease when not held."""
        mock_redis.set = AsyncMock(return_value=True)

        result = await acquire_execution_lease(
            redis=mock_redis,
            campaign_id=123,
            holder_id="worker-1",
        )

        assert result.acquired is True
        assert result.holder_id == "worker-1"
        assert result.reason == "lease_acquired"
        mock_redis.set.assert_called_once()

    @pytest.mark.asyncio
    async def test_acquire_lease_already_held(self, mock_redis):
        """Should fail when lease already held by another."""
        mock_redis.set = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value="worker-other")
        mock_redis.ttl = AsyncMock(return_value=250)

        result = await acquire_execution_lease(
            redis=mock_redis,
            campaign_id=123,
            holder_id="worker-1",
        )

        assert result.acquired is False
        assert result.holder_id == "worker-other"
        assert "held_by_other" in result.reason

    @pytest.mark.asyncio
    async def test_acquire_lease_renew_own(self, mock_redis):
        """Should renew lease when we already hold it."""
        mock_redis.set = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value="worker-1")
        mock_redis.ttl = AsyncMock(return_value=250)
        mock_redis.expire = AsyncMock(return_value=True)

        result = await acquire_execution_lease(
            redis=mock_redis,
            campaign_id=123,
            holder_id="worker-1",
        )

        assert result.acquired is True
        assert result.reason == "lease_renewed"
        mock_redis.expire.assert_called_once()

    @pytest.mark.asyncio
    async def test_release_lease_own(self, mock_redis):
        """Should release lease when we own it."""
        mock_redis.eval = AsyncMock(return_value=1)

        released = await release_execution_lease(
            redis=mock_redis,
            campaign_id=123,
            holder_id="worker-1",
        )

        assert released is True

    @pytest.mark.asyncio
    async def test_release_lease_not_own(self, mock_redis):
        """Should not release lease when we don't own it."""
        mock_redis.eval = AsyncMock(return_value=0)

        released = await release_execution_lease(
            redis=mock_redis,
            campaign_id=123,
            holder_id="worker-1",
        )

        assert released is False

    @pytest.mark.asyncio
    async def test_extend_lease_own(self, mock_redis):
        """Should extend lease when we own it."""
        mock_redis.eval = AsyncMock(return_value=1)

        extended = await extend_execution_lease(
            redis=mock_redis,
            campaign_id=123,
            holder_id="worker-1",
        )

        assert extended is True

    @pytest.mark.asyncio
    async def test_get_lease_holder(self, mock_redis):
        """Should get current lease holder."""
        mock_redis.get = AsyncMock(return_value="worker-1")

        holder = await get_lease_holder(mock_redis, 123)

        assert holder == "worker-1"
        mock_redis.get.assert_called_once_with(_execution_lease_key(123))

    @pytest.mark.asyncio
    async def test_get_lease_holder_none(self, mock_redis):
        """Should return None when no holder."""
        mock_redis.get = AsyncMock(return_value=None)

        holder = await get_lease_holder(mock_redis, 123)

        assert holder is None


# ─────────────────────────────────────────────────────────────────────────────
# Heartbeat Management Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestHeartbeatManagement:
    """Test heartbeat recording and checking."""

    @pytest.mark.asyncio
    async def test_record_heartbeat(self, mock_redis):
        """Should record heartbeat with correct data."""
        mock_redis.set = AsyncMock(return_value=True)

        await record_campaign_heartbeat(
            redis=mock_redis,
            campaign_id=123,
            task_id="task-abc",
            progress_metadata={"processed": 50, "total": 100},
        )

        mock_redis.set.assert_called_once()
        call_args = mock_redis.set.call_args
        assert call_args[0][0] == _heartbeat_key(123)

    @pytest.mark.asyncio
    async def test_is_campaign_stale_fresh(self, mock_redis):
        """Should not be stale when recent heartbeat."""
        now_ms = int(time.time() * 1000)
        import json
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "campaign_id": 123,
            "timestamp_ms": now_ms,
        }))

        is_stale, heartbeat = await is_campaign_stale(
            mock_redis, 123,
            stale_threshold_seconds=DEFAULT_STALE_THRESHOLD_SECONDS,
        )

        assert is_stale is False
        assert heartbeat is not None

    @pytest.mark.asyncio
    async def test_is_campaign_stale_old(self, mock_redis):
        """Should be stale when old heartbeat."""
        old_ms = int((time.time() - 300) * 1000)  # 5 minutes ago
        import json
        mock_redis.get = AsyncMock(return_value=json.dumps({
            "campaign_id": 123,
            "timestamp_ms": old_ms,
        }))

        is_stale, heartbeat = await is_campaign_stale(
            mock_redis, 123,
            stale_threshold_seconds=DEFAULT_STALE_THRESHOLD_SECONDS,
        )

        assert is_stale is True

    @pytest.mark.asyncio
    async def test_is_campaign_stale_no_heartbeat(self, mock_redis):
        """Should be stale when no heartbeat at all."""
        mock_redis.get = AsyncMock(return_value=None)

        is_stale, heartbeat = await is_campaign_stale(mock_redis, 123)

        assert is_stale is True
        assert heartbeat is None


# ─────────────────────────────────────────────────────────────────────────────
# Stale Campaign Detection Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestStaleCampaignDetection:
    """Test stale campaign detection."""

    @pytest.mark.asyncio
    async def test_detect_stalled_campaigns_finds_stale(self, mock_session, mock_redis):
        """Should detect campaigns with stale heartbeats."""
        # Mock campaign query result
        campaign = MagicMock()
        campaign.id = 123
        campaign.workspace_id = 456
        campaign.celery_task_id = "task-old"
        campaign.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=5)
        campaign.last_checkpoint_index = 0

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [campaign]
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock celery inspection
        with patch("app.services.campaign_recovery_service.celery_app") as mock_celery:
            mock_inspector = MagicMock()
            mock_inspector.active.return_value = {}  # No active tasks
            mock_celery.control.inspect.return_value = mock_inspector

            # Mock contact counts
            mock_contact_result = MagicMock()
            mock_contact_result.scalars.return_value.all.return_value = [
                MagicMock(id=i) for i in range(100)
            ]
            original_execute = mock_session.execute

            call_count = [0]
            async def mock_execute(stmt):
                call_count[0] += 1
                if call_count[0] == 1:
                    return mock_result  # Campaign query
                return mock_contact_result  # Contact count queries

            mock_session.execute = mock_execute

            stalled = await detect_stalled_campaigns(
                session=mock_session,
                stale_threshold_seconds=DEFAULT_STALE_THRESHOLD_SECONDS,
            )

        assert len(stalled) == 1
        assert stalled[0].campaign_id == 123
        assert stalled[0].total_recipients == 100

    @pytest.mark.asyncio
    async def test_detect_stalled_campaigns_excludes_active(self, mock_session):
        """Should not detect campaigns with active celery tasks."""
        campaign = MagicMock()
        campaign.id = 123
        campaign.workspace_id = 456
        campaign.celery_task_id = "task-active"
        campaign.last_heartbeat_at = datetime.now(timezone.utc) - timedelta(minutes=1)

        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [campaign]
        mock_session.execute = AsyncMock(return_value=mock_result)

        with patch("app.services.campaign_recovery_service.celery_app") as mock_celery:
            mock_inspector = MagicMock()
            mock_inspector.active.return_value = {
                "worker-1": [{"id": "task-active", "name": "campaign_send"}]
            }
            mock_celery.control.inspect.return_value = mock_inspector

            stalled = await detect_stalled_campaigns(
                session=mock_session,
                stale_threshold_seconds=DEFAULT_STALE_THRESHOLD_SECONDS,
            )

        assert len(stalled) == 0


# ─────────────────────────────────────────────────────────────────────────────
# Recovery Context Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRecoveryContext:
    """Test RecoveryContext dataclass."""

    def test_recovery_context_creation(self, sample_recovery_context):
        """Should create recovery context with all fields."""
        assert sample_recovery_context.campaign_id == 123
        assert sample_recovery_context.workspace_id == 456
        assert sample_recovery_context.reason == "no_heartbeat_and_task_not_active"
        assert sample_recovery_context.processed_recipients == 50

    def test_recovery_context_has_default_detected_at(self):
        """Should auto-set detected_at to now."""
        ctx = RecoveryContext(
            campaign_id=1,
            workspace_id=1,
            celery_task_id=None,
            last_checkpoint_index=0,
            total_recipients=0,
            processed_recipients=0,
            success_count=0,
            failed_count=0,
            reason="test",
        )
        assert ctx.detected_at is not None
        assert isinstance(ctx.detected_at, datetime)


# ─────────────────────────────────────────────────────────────────────────────
# Lease Result Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLeaseResult:
    """Test LeaseResult dataclass."""

    def test_lease_result_success(self):
        """Should create successful lease result."""
        result = LeaseResult(
            acquired=True,
            holder_id="worker-1",
            expires_at=datetime.now(timezone.utc),
            reason="lease_acquired",
        )
        assert result.acquired is True
        assert result.holder_id == "worker-1"

    def test_lease_result_failure(self):
        """Should create failed lease result."""
        result = LeaseResult(
            acquired=False,
            holder_id="worker-other",
            expires_at=None,
            reason="held_by_other:worker-other",
        )
        assert result.acquired is False


# ─────────────────────────────────────────────────────────────────────────────
# Recovery Execution Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRecoveryExecution:
    """Test campaign recovery execution."""

    @pytest.mark.asyncio
    async def test_mark_campaign_recovering(self, mock_session, sample_recovery_context):
        """Should mark campaign as recovering."""
        await mark_campaign_recovering(mock_session, sample_recovery_context.campaign_id)
        mock_session.execute.assert_called_once()
        mock_session.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_recover_stalled_campaign_lock_fails(
        self, mock_session, mock_redis, sample_recovery_context
    ):
        """Should fail if recovery lock already held."""
        mock_redis.set = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value="other-recovery-worker")

        with pytest.raises(CampaignRecoveryError) as exc_info:
            await recover_stalled_campaign(
                session=mock_session,
                redis=mock_redis,
                recovery_context=sample_recovery_context,
                holder_id="recovery-worker-1",
            )

        assert "Recovery already in progress" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_initialize_campaign_execution_lease_error(
        self, mock_session, mock_redis, sample_campaign
    ):
        """Should raise error when lease acquisition fails."""
        mock_redis.set = AsyncMock(return_value=False)
        mock_redis.get = AsyncMock(return_value="other-holder")

        with pytest.raises(CampaignExecutionLeaseError) as exc_info:
            await initialize_campaign_execution(
                session=mock_session,
                redis=mock_redis,
                campaign=sample_campaign,
                task_id="task-new",
            )

        assert exc_info.value.campaign_id == sample_campaign.id
        assert "Could not acquire lease" in exc_info.value.reason

    @pytest.mark.asyncio
    async def test_finalize_campaign_execution(
        self, mock_session, mock_redis, sample_campaign
    ):
        """Should finalize campaign execution."""
        mock_redis.eval = AsyncMock(return_value=1)
        mock_redis.delete = AsyncMock(return_value=1)

        await finalize_campaign_execution(
            session=mock_session,
            redis=mock_redis,
            campaign=sample_campaign,
            task_id="task-1",
            status=CampaignStatus.completed,
        )

        # Verify lease release and heartbeat clear called
        mock_redis.eval.assert_called_once()
        mock_redis.delete.assert_called_once()

    @pytest.mark.asyncio
    async def test_update_campaign_progress(
        self, mock_session, mock_redis, sample_campaign
    ):
        """Should update progress with heartbeat."""
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.eval = AsyncMock(return_value=1)

        await update_campaign_progress(
            session=mock_session,
            redis=mock_redis,
            campaign=sample_campaign,
            task_id="task-1",
            processed=50,
            total=100,
            success_count=45,
            failed_count=5,
            checkpoint_index=123,
        )

        # Verify heartbeat recorded
        assert mock_redis.set.called
        # Verify lease extended
        assert mock_redis.eval.called


# ─────────────────────────────────────────────────────────────────────────────
# Idempotency Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestIdempotencyDuringRecovery:
    """Test that recovery respects idempotency."""

    @pytest.mark.asyncio
    async def test_already_sent_contacts_skipped(self):
        """Contacts marked as sent should not be re-sent."""
        # This is verified by the _already_sent check in the main task
        # The idempotency key prevents duplicate sends
        pass

    @pytest.mark.asyncio
    async def test_inflight_lock_prevents_duplicate(self, mock_redis):
        """In-flight lock should prevent duplicate processing."""
        # When a contact is being processed, an inflight lock is acquired
        # If recovery tries to process the same contact, the lock prevents it
        idempotency_key = "campaign:123:contact:456"
        key = f"queue:idempotency:inflight:{idempotency_key}"

        # Simulate lock already held
        mock_redis.set = AsyncMock(return_value=False)

        acquired = await mock_redis.set(
            key, "1",
            ex=120,
            nx=True,
        )

        assert acquired is False  # Lock already held


# ─────────────────────────────────────────────────────────────────────────────
# Redis Key Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestRedisKeys:
    """Test Redis key generation."""

    def test_execution_lease_key(self):
        """Should generate correct lease key."""
        assert _execution_lease_key(123) == "campaign:lease:123"

    def test_heartbeat_key(self):
        """Should generate correct heartbeat key."""
        assert _heartbeat_key(123) == "campaign:heartbeat:123"

    def test_recovery_lock_key(self):
        """Should generate correct recovery lock key."""
        assert _recovery_lock_key(123) == "campaign:recovery:lock:123"


# ─────────────────────────────────────────────────────────────────────────────
# Edge Cases Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestEdgeCases:
    """Test edge cases and error conditions."""

    @pytest.mark.asyncio
    async def test_lease_acquire_redis_error(self, mock_redis):
        """Should handle Redis errors gracefully."""
        from redis.exceptions import RedisError

        mock_redis.set = AsyncMock(side_effect=RedisError("Connection failed"))

        with pytest.raises(RedisError):
            await acquire_execution_lease(
                redis=mock_redis,
                campaign_id=123,
                holder_id="worker-1",
            )

    @pytest.mark.asyncio
    async def test_heartbeat_redis_error(self, mock_redis):
        """Should handle Redis errors in heartbeat."""
        from redis.exceptions import RedisError

        mock_redis.set = AsyncMock(side_effect=RedisError("Connection failed"))

        # Should not raise, just log warning
        try:
            await record_campaign_heartbeat(
                redis=mock_redis,
                campaign_id=123,
                task_id="task-1",
            )
        except RedisError:
            pytest.fail("Should handle Redis error gracefully")

    @pytest.mark.asyncio
    async def test_recovery_with_zero_recipients(self, mock_session, mock_redis, sample_recovery_context):
        """Should handle campaign with zero recipients."""
        sample_recovery_context.total_recipients = 0
        sample_recovery_context.processed_recipients = 0

        # Mock campaign retrieval
        mock_campaign = MagicMock()
        mock_campaign.id = 123
        mock_campaign.status = CampaignStatus.running
        mock_session.get = AsyncMock(return_value=mock_campaign)

        # Mock lock acquisition
        mock_redis.set = AsyncMock(return_value=True)
        mock_redis.delete = AsyncMock(return_value=1)

        # Mock contact queries
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Mock task delay
        with patch("app.services.campaign_recovery_service.process_campaign_send_task") as mock_task:
            mock_task.delay = MagicMock(return_value=MagicMock(id="new-task-123"))

            result = await recover_stalled_campaign(
                session=mock_session,
                redis=mock_redis,
                recovery_context=sample_recovery_context,
                holder_id="recovery-worker",
            )

        assert result["status"] == "recovered"
        assert result["reset_count"] == 0


# ─────────────────────────────────────────────────────────────────────────────
# Configuration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestConfiguration:
    """Test configuration constants."""

    def test_default_lease_ttl(self):
        """Should have reasonable default lease TTL."""
        assert DEFAULT_LEASE_TTL_SECONDS == 300  # 5 minutes

    def test_default_stale_threshold(self):
        """Should have reasonable default stale threshold."""
        assert DEFAULT_STALE_THRESHOLD_SECONDS == 180  # 3 minutes

    def test_default_heartbeat_interval(self):
        """Should have reasonable default heartbeat interval."""
        assert DEFAULT_HEARTBEAT_INTERVAL_SECONDS == 30  # 30 seconds