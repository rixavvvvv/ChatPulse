"""
Campaign execution recovery service.

Handles stalled campaign detection and recovery after:
- Worker crashes (OOM, SIGKILL, container restart)
- Infrastructure restarts
- Stuck execution loops
- Network partitions

Key concepts:
1. Heartbeat timestamps: Updated during campaign execution
2. Execution leases: Redis-based locks with TTL
3. Recovery workers: Dedicated workers for stalled campaign recovery
4. Safe resume points: Determined by checkpoint progress

Recovery flow:
1. Detect stalled campaigns (running status + stale heartbeat)
2. Acquire execution lease (Redis SETNX)
3. Requeue unfinished recipients
4. Resume from last checkpoint
5. Prevent duplicate sends via idempotency keys
"""

from __future__ import annotations

import asyncio
import logging
import math
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import AsyncSessionLocal
from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_contact import (
    CampaignContact,
    CampaignContactDeliveryStatus,
)
from app.queue.registry import TASKS

logger = logging.getLogger(__name__)
settings = get_settings()

# Redis key patterns for campaign execution management
_EXECUTION_LEASE_PREFIX = "campaign:lease"
_HEARTBEAT_KEY_PREFIX = "campaign:heartbeat"
_RECOVERY_LOCK_PREFIX = "campaign:recovery:lock"
_STALLED_CAMPAIGN_PREFIX = "campaign:stalled"

# Default timeouts
DEFAULT_LEASE_TTL_SECONDS = 300  # 5 minutes - worker must heartbeat within this
DEFAULT_STALE_THRESHOLD_SECONDS = 180  # 3 minutes - consider stalled if no heartbeat
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 30  # Worker should heartbeat every 30 seconds


def _execution_lease_key(campaign_id: int) -> str:
    return f"{_EXECUTION_LEASE_PREFIX}:{campaign_id}"


def _heartbeat_key(campaign_id: int) -> str:
    return f"{_HEARTBEAT_KEY_PREFIX}:{campaign_id}"


def _recovery_lock_key(campaign_id: int) -> str:
    return f"{_RECOVERY_LOCK_PREFIX}:{campaign_id}"


def _stalled_campaign_key() -> str:
    return f"{_STALLED_CAMPAIGN_PREFIX}:detected"


@dataclass
class RecoveryContext:
    """Context for campaign recovery operation."""
    campaign_id: int
    workspace_id: int
    celery_task_id: str | None
    last_checkpoint_index: int
    total_recipients: int
    processed_recipients: int
    success_count: int
    failed_count: int
    reason: str
    detected_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class LeaseResult:
    """Result of lease acquisition attempt."""
    acquired: bool
    holder_id: str | None
    expires_at: datetime | None
    reason: str


class CampaignExecutionLeaseError(Exception):
    """Raised when lease acquisition fails."""
    def __init__(self, campaign_id: int, reason: str):
        self.campaign_id = campaign_id
        self.reason = reason
        super().__init__(f"Lease error for campaign {campaign_id}: {reason}")


class CampaignRecoveryError(Exception):
    """Raised when recovery fails."""
    def __init__(self, campaign_id: int, reason: str):
        self.campaign_id = campaign_id
        self.reason = reason
        super().__init__(f"Recovery error for campaign {campaign_id}: {reason}")


# ============================================================================
# LEASE MANAGEMENT
# ============================================================================

async def acquire_execution_lease(
    redis: Redis,
    campaign_id: int,
    holder_id: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> LeaseResult:
    """
    Acquire execution lease for campaign.

    Uses Redis SETNX for atomic lock acquisition.
    Only one worker can hold the lease at a time.
    """
    key = _execution_lease_key(campaign_id)
    now = datetime.now(tz=UTC)
    expires_at = datetime.fromtimestamp(time.time() + ttl_seconds, tz=UTC)

    # Try to acquire lease atomically
    acquired = await redis.set(
        key,
        holder_id,
        ex=ttl_seconds,
        nx=True,
    )

    if acquired:
        logger.info(
            "Execution lease acquired campaign_id=%s holder=%s ttl=%ds",
            campaign_id, holder_id, ttl_seconds
        )
        return LeaseResult(
            acquired=True,
            holder_id=holder_id,
            expires_at=expires_at,
            reason="lease_acquired",
        )

    # Lease already held - check if expired or by another holder
    current_holder = await redis.get(key)
    ttl_remaining = await redis.ttl(key)

    if current_holder == holder_id:
        # Renew our own lease
        await redis.expire(key, ttl_seconds)
        return LeaseResult(
            acquired=True,
            holder_id=holder_id,
            expires_at=expires_at,
            reason="lease_renewed",
        )

    return LeaseResult(
        acquired=False,
        holder_id=current_holder,
        expires_at=datetime.fromtimestamp(
            time.time() + (ttl_remaining if ttl_remaining > 0 else 0),
            tz=UTC
        ) if ttl_remaining > 0 else None,
        reason=f"held_by_other:{current_holder}",
    )


async def release_execution_lease(
    redis: Redis,
    campaign_id: int,
    holder_id: str,
) -> bool:
    """
    Release execution lease for campaign.

    Only releases if we own the lease.
    Uses Lua script for atomic check-and-delete.
    """
    key = _execution_lease_key(campaign_id)

    # Lua script: only delete if value matches holder_id
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("del", KEYS[1])
    else
        return 0
    end
    """
    result = await redis.eval(lua_script, 1, key, holder_id)
    return bool(result)


async def extend_execution_lease(
    redis: Redis,
    campaign_id: int,
    holder_id: str,
    ttl_seconds: int = DEFAULT_LEASE_TTL_SECONDS,
) -> bool:
    """
    Extend execution lease if we own it.

    Uses Lua script for atomic check-and-extend.
    """
    key = _execution_lease_key(campaign_id)

    # Lua script: only extend if value matches holder_id
    lua_script = """
    if redis.call("get", KEYS[1]) == ARGV[1] then
        return redis.call("expire", KEYS[1], ARGV[2])
    else
        return 0
    end
    """
    result = await redis.eval(lua_script, 1, key, holder_id, ttl_seconds)
    return bool(result)


async def get_lease_holder(redis: Redis, campaign_id: int) -> str | None:
    """Get current lease holder for campaign."""
    key = _execution_lease_key(campaign_id)
    return await redis.get(key)


# ============================================================================
# HEARTBEAT MANAGEMENT
# ============================================================================

async def record_campaign_heartbeat(
    redis: Redis,
    campaign_id: int,
    task_id: str,
    progress_metadata: dict[str, Any] | None = None,
    ttl_seconds: int = DEFAULT_STALE_THRESHOLD_SECONDS * 3,
) -> None:
    """
    Record campaign execution heartbeat.

    Workers should call this periodically (every 30 seconds)
    during campaign execution. The heartbeat is used to detect
    stalled campaigns.
    """
    key = _heartbeat_key(campaign_id)
    now_ms = int(time.time() * 1000)

    data = {
        "campaign_id": campaign_id,
        "task_id": task_id,
        "timestamp_ms": now_ms,
        "updated_at": datetime.now(tz=UTC).isoformat(),
        "metadata": progress_metadata or {},
    }

    import json
    await redis.set(key, json.dumps(data), ex=ttl_seconds)


async def get_campaign_heartbeat(redis: Redis, campaign_id: int) -> dict[str, Any] | None:
    """Get campaign heartbeat data."""
    key = _heartbeat_key(campaign_id)
    import json
    data = await redis.get(key)
    return json.loads(data) if data else None


async def is_campaign_stale(
    redis: Redis,
    campaign_id: int,
    stale_threshold_seconds: int = DEFAULT_STALE_THRESHOLD_SECONDS,
) -> tuple[bool, dict[str, Any] | None]:
    """
    Check if campaign is stale (no recent heartbeat).

    Returns (is_stale, heartbeat_data).
    """
    heartbeat = await get_campaign_heartbeat(redis, campaign_id)

    if not heartbeat:
        return True, None

    last_timestamp_ms = heartbeat.get("timestamp_ms", 0)
    now_ms = int(time.time() * 1000)
    age_seconds = (now_ms - last_timestamp_ms) / 1000

    is_stale = age_seconds > stale_threshold_seconds
    return is_stale, heartbeat


# ============================================================================
# STALLED CAMPAIGN DETECTION
# ============================================================================

async def detect_stalled_campaigns(
    session: AsyncSession,
    stale_threshold_seconds: int = DEFAULT_STALE_THRESHOLD_SECONDS,
) -> list[RecoveryContext]:
    """
    Detect campaigns that are stalled (running but not making progress).

    A campaign is considered stalled if:
    1. Status is 'running'
    2. No heartbeat received within stale_threshold_seconds
    3. Celery task is no longer active
    """
    from app.queue.celery_app import celery_app

    now = datetime.now(tz=UTC)
    stale_threshold = timedelta(seconds=stale_threshold_seconds)
    cutoff_time = now - stale_threshold

    # Find running campaigns with stale heartbeats
    stmt = (
        select(Campaign)
        .where(
            Campaign.status == CampaignStatus.running,
            Campaign.last_heartbeat_at < cutoff_time,
        )
        .limit(100)  # Process in batches
    )
    result = await session.execute(stmt)
    stale_campaigns = result.scalars().all()

    recovery_contexts = []

    for campaign in stale_campaigns:
        try:
            # Check if celery task is still active
            task_id = campaign.celery_task_id
            task_is_active = False

            if task_id:
                try:
                    inspector = celery_app.control.inspect(timeout=1.0)
                    if inspector:
                        active_tasks = inspector.active()
                        if active_tasks:
                            for worker, tasks in active_tasks.items():
                                for task in tasks:
                                    if task.get("id") == task_id:
                                        task_is_active = True
                                        break
                except Exception:
                    pass

            if not task_is_active:
                # Count processed vs total recipients
                total_result = await session.execute(
                    select(CampaignContact)
                    .where(CampaignContact.campaign_id == campaign.id)
                )
                total_contacts = list(total_result.scalars().all())

                processed_result = await session.execute(
                    select(CampaignContact)
                    .where(
                        CampaignContact.campaign_id == campaign.id,
                        CampaignContact.delivery_status.in_([
                            CampaignContactDeliveryStatus.sent,
                            CampaignContactDeliveryStatus.failed,
                            CampaignContactDeliveryStatus.skipped,
                        ])
                    )
                )
                processed_contacts = list(processed_result.scalars().all())

                recovery_contexts.append(RecoveryContext(
                    campaign_id=campaign.id,
                    workspace_id=campaign.workspace_id,
                    celery_task_id=task_id,
                    last_checkpoint_index=campaign.last_checkpoint_index or 0,
                    total_recipients=len(total_contacts),
                    processed_recipients=len(processed_contacts),
                    success_count=campaign.success_count or 0,
                    failed_count=campaign.failed_count or 0,
                    reason="no_heartbeat_and_task_not_active",
                    detected_at=now,
                ))
        except Exception as exc:
            logger.warning(
                "Error checking campaign %s for staleness: %s",
                campaign.id, exc
            )

    return recovery_contexts


async def mark_campaign_recovering(
    session: AsyncSession,
    campaign_id: int,
) -> None:
    """Mark campaign as recovering."""
    await session.execute(
        update(Campaign)
        .where(Campaign.id == campaign_id)
        .values(
            status=CampaignStatus.recovering,
            recovery_count=Campaign.recovery_count + 1,
            last_recovered_at=datetime.now(tz=UTC),
        )
    )


# ============================================================================
# RECOVERY EXECUTION
# ============================================================================

async def recover_stalled_campaign(
    session: AsyncSession,
    redis: Redis,
    recovery_context: RecoveryContext,
    holder_id: str,
) -> dict[str, Any]:
    """
    Recover a stalled campaign.

    Steps:
    1. Acquire recovery lock
    2. Determine safe resume point
    3. Reset pending recipients
    4. Requeue campaign send task
    5. Return recovery summary
    """
    from app.queue.tasks import process_campaign_send_task

    campaign_id = recovery_context.campaign_id

    # Try to acquire recovery lock (prevents concurrent recovery attempts)
    lock_key = _recovery_lock_key(campaign_id)
    lock_acquired = await redis.set(
        lock_key,
        holder_id,
        ex=600,  # 10 minute lock
        nx=True,
    )

    if not lock_acquired:
        current_holder = await redis.get(lock_key)
        raise CampaignRecoveryError(
            campaign_id,
            f"Recovery already in progress by {current_holder}"
        )

    try:
        # Get campaign record
        campaign = await session.get(Campaign, campaign_id)
        if not campaign:
            raise CampaignRecoveryError(campaign_id, "Campaign not found")

        # Determine safe resume point
        resume_index = await _determine_safe_resume_point(
            session, campaign_id, recovery_context.last_checkpoint_index
        )

        # Reset pending recipients (they may need re-processing)
        reset_count = await _reset_pending_recipients(
            session, campaign_id, resume_index
        )

        # Update campaign record
        campaign.status = CampaignStatus.running
        campaign.celery_task_id = None  # Will be set by new task
        campaign.last_checkpoint_index = resume_index
        campaign.last_heartbeat_at = datetime.now(tz=UTC)
        await session.commit()

        # Clear old heartbeats
        await redis.delete(_heartbeat_key(campaign_id))

        # Requeue campaign send task
        task = process_campaign_send_task.delay(
            workspace_id=recovery_context.workspace_id,
            campaign_id=campaign_id,
        )

        # Update celery task ID
        campaign.celery_task_id = task.id
        await session.commit()

        logger.info(
            "Campaign recovery initiated campaign_id=%s resume_index=%d "
            "reset_count=%d new_task_id=%s",
            campaign_id, resume_index, reset_count, task.id
        )

        return {
            "campaign_id": campaign_id,
            "status": "recovered",
            "resume_index": resume_index,
            "reset_count": reset_count,
            "new_celery_task_id": task.id,
            "previous_success_count": recovery_context.success_count,
            "previous_failed_count": recovery_context.failed_count,
        }

    finally:
        # Release recovery lock
        await redis.delete(lock_key)


async def _determine_safe_resume_point(
    session: AsyncSession,
    campaign_id: int,
    last_checkpoint_index: int,
) -> int:
    """
    Determine safe point to resume campaign execution.

    Uses idempotency keys to find the last successfully sent contact.
    Resume point is the first contact that hasn't been marked as sent.
    """
    # Find the last contact that was successfully sent
    stmt = (
        select(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.delivery_status == CampaignContactDeliveryStatus.sent,
        )
        .order_by(CampaignContact.id.asc())
    )
    result = await session.execute(stmt)
    sent_contacts = list(result.scalars().all())

    if sent_contacts:
        # Resume from the next contact after the last sent
        last_sent_id = sent_contacts[-1].id
        return last_sent_id

    # If no contacts sent yet, start from beginning or checkpoint
    return last_checkpoint_index


async def _reset_pending_recipients(
    session: AsyncSession,
    campaign_id: int,
    resume_index: int,
) -> int:
    """
    Reset pending recipients to allow re-processing.

    Only resets contacts with 'pending' status that are at or after resume_index.
    Already sent/failed contacts are left as-is (idempotency prevents re-send).
    """
    from app.models.base import Base
    from sqlalchemy import update as sql_update

    # Reset pending contacts (they haven't been processed yet)
    stmt = (
        sql_update(CampaignContact)
        .where(
            CampaignContact.campaign_id == campaign_id,
            CampaignContact.delivery_status == CampaignContactDeliveryStatus.pending,
            CampaignContact.id >= resume_index,
        )
        .values(
            delivery_status=CampaignContactDeliveryStatus.pending,
            attempt_count=0,
            last_error=None,
            failure_classification=None,
        )
    )
    result = await session.execute(stmt)
    return result.rowcount


# ============================================================================
# RECOVERY WORKER
# ============================================================================

async def run_recovery_worker(
    stale_threshold_seconds: int = DEFAULT_STALE_THRESHOLD_SECONDS,
    poll_interval_seconds: int = 60,
    max_concurrent_recoveries: int = 5,
) -> None:
    """
    Background worker that detects and recovers stalled campaigns.

    This should run as a separate Celery task on a dedicated worker.

    Args:
        stale_threshold_seconds: Consider stalled if no heartbeat for this duration
        poll_interval_seconds: How often to check for stalled campaigns
        max_concurrent_recoveries: Maximum number of concurrent recovery operations
    """
    holder_id = f"recovery-worker-{time.time()}"

    while True:
        try:
            async with AsyncSessionLocal() as session:
                # Detect stalled campaigns
                stalled_campaigns = await detect_stalled_campaigns(
                    session, stale_threshold_seconds
                )

                if stalled_campaigns:
                    logger.info(
                        "Detected %d stalled campaigns",
                        len(stalled_campaigns)
                    )

                    for recovery_context in stalled_campaigns[:max_concurrent_recoveries]:
                        try:
                            # Mark as recovering
                            await mark_campaign_recovering(
                                session, recovery_context.campaign_id
                            )
                            await session.commit()

                            # Execute recovery
                            result = await recover_stalled_campaign(
                                session=session,
                                redis=Redis.from_url(
                                    settings.redis_url,
                                    decode_responses=True
                                ),
                                recovery_context=recovery_context,
                                holder_id=holder_id,
                            )

                            logger.info(
                                "Campaign recovered campaign_id=%s result=%s",
                                recovery_context.campaign_id, result
                            )

                        except Exception as exc:
                            logger.error(
                                "Failed to recover campaign %s: %s",
                                recovery_context.campaign_id, exc
                            )

                # Update stalled campaign counter for metrics
                if stalled_campaigns:
                    redis = Redis.from_url(settings.redis_url)
                    try:
                        await redis.incrby(
                            _stalled_campaign_key(),
                            len(stalled_campaigns)
                        )
                        await redis.expire(_stalled_campaign_key(), 3600)
                    finally:
                        await redis.aclose()

        except Exception as exc:
            logger.error("Recovery worker error: %s", exc)

        await asyncio.sleep(poll_interval_seconds)


def start_recovery_worker() -> None:
    """Start the recovery worker (blocking)."""
    import asyncio
    asyncio.run(run_recovery_worker())


# ============================================================================
# CAMPAIGN EXECUTION INTEGRATION
# ============================================================================

async def initialize_campaign_execution(
    session: AsyncSession,
    redis: Redis,
    campaign: Campaign,
    task_id: str,
) -> None:
    """
    Initialize campaign execution: acquire lease, set up heartbeat tracking.

    Called at the start of campaign send task.
    """
    # Acquire execution lease
    lease_result = await acquire_execution_lease(
        redis, campaign.id, task_id
    )

    if not lease_result.acquired:
        raise CampaignExecutionLeaseError(
            campaign.id,
            f"Could not acquire lease: {lease_result.reason}"
        )

    # Initialize heartbeat
    await record_campaign_heartbeat(
        redis, campaign.id, task_id,
        progress_metadata={
            "status": "starting",
            "total_recipients": 0,
        }
    )

    # Update campaign with execution info
    campaign.celery_task_id = task_id
    campaign.last_heartbeat_at = datetime.now(tz=UTC)
    campaign.execution_lease_expires_at = lease_result.expires_at
    await session.commit()


async def update_campaign_progress(
    session: AsyncSession,
    redis: Redis,
    campaign: Campaign,
    task_id: str,
    processed: int,
    total: int,
    success_count: int,
    failed_count: int,
    checkpoint_index: int,
) -> None:
    """
    Update campaign progress: heartbeat, checkpoint, aggregate counters.

    Called periodically during campaign execution.
    """
    # Update heartbeat
    await record_campaign_heartbeat(
        redis, campaign.id, task_id,
        progress_metadata={
            "processed": processed,
            "total": total,
            "success": success_count,
            "failed": failed_count,
            "progress_pct": (processed / total * 100) if total > 0 else 0,
        }
    )

    # Update campaign record
    campaign.success_count = success_count
    campaign.failed_count = failed_count
    campaign.last_heartbeat_at = datetime.now(tz=UTC)
    campaign.last_checkpoint_index = checkpoint_index
    await session.commit()

    # Extend lease
    await extend_execution_lease(redis, campaign.id, task_id)


async def finalize_campaign_execution(
    session: AsyncSession,
    redis: Redis,
    campaign: Campaign,
    task_id: str,
    status: CampaignStatus,
) -> None:
    """
    Finalize campaign execution: release lease, clear heartbeat.

    Called at the end of campaign send task (success or failure).
    """
    # Release execution lease
    await release_execution_lease(redis, campaign.id, task_id)

    # Clear heartbeat
    await redis.delete(_heartbeat_key(campaign.id))

    # Update campaign status
    campaign.status = status
    campaign.execution_lease_expires_at = None
    await session.commit()


# ============================================================================
# METRICS AND AUDIT
# ============================================================================

async def get_recovery_metrics(redis: Redis) -> dict[str, Any]:
    """Get recovery-related metrics from Redis."""
    stalled_count = await redis.get(_stalled_campaign_key())

    return {
        "stalled_campaigns_detected_1h": int(stalled_count) if stalled_count else 0,
        "recovery_worker_status": "running",  # Would need actual health check
    }


async def log_recovery_audit(
    session: AsyncSession,
    campaign_id: int,
    action: str,
    details: dict[str, Any],
) -> None:
    """Log recovery action for audit trail."""
    from app.models.domain_event import DomainEvent

    event = DomainEvent(
        workspace_id=details.get("workspace_id", 0),
        event_type=f"campaign.recovery.{action}",
        payload={
            "campaign_id": campaign_id,
            "action": action,
            "details": details,
            "timestamp": datetime.now(tz=UTC).isoformat(),
        },
    )
    session.add(event)
    await session.commit()