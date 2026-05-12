"""
Campaign recovery Celery tasks.

Provides async recovery worker and manual recovery triggers.
"""

from __future__ import annotations

import asyncio

from app.core.config import get_settings
from app.db import engine
from app.queue.celery_app import celery_app
from app.queue.registry import TASKS
from app.services.campaign_recovery_service import (
    DEFAULT_STALE_THRESHOLD_SECONDS,
    detect_stalled_campaigns,
    mark_campaign_recovering,
    recover_stalled_campaign,
    run_recovery_worker,
)

settings = get_settings()


async def _dispose_engine() -> None:
    await engine.dispose()


def _run_with_engine_reset(coro):
    async def _runner():
        try:
            return await coro
        finally:
            try:
                await _dispose_engine()
            except Exception:
                pass
    return asyncio.run(_runner())


class CampaignRecoveryTask:
    """Base task for campaign recovery operations."""
    abstract = True
    acks_late = True
    reject_on_worker_lost = True


@celery_app.task(
    bind=True,
    base=CampaignRecoveryTask,
    name=TASKS.campaign_recovery_check,
    max_retries=5,
    retry_backoff=True,
)
def check_stalled_campaigns_task(self) -> dict:
    """
    Periodic task to detect and recover stalled campaigns.

    This task runs on a schedule (e.g., every 60 seconds) to:
    1. Detect running campaigns with stale heartbeats
    2. Mark them as recovering
    3. Trigger recovery for each stalled campaign
    """
    from redis.asyncio import Redis

    try:
        from app.db import AsyncSessionLocal

        async def _run():
            stale_threshold = settings.queue_stale_campaign_threshold_seconds or DEFAULT_STALE_THRESHOLD_SECONDS

            async with AsyncSessionLocal() as session:
                # Detect stalled campaigns
                stalled = await detect_stalled_campaigns(session, stale_threshold)

                if not stalled:
                    return {"status": "ok", "stalled_count": 0, "recovered_count": 0}

                recovered = 0
                errors = []

                for context in stalled:
                    try:
                        await mark_campaign_recovering(session, context.campaign_id)
                        await session.commit()

                        redis = Redis.from_url(settings.redis_url, decode_responses=True)
                        try:
                            holder_id = f"task-{self.request.id}"
                            result = await recover_stalled_campaign(
                                session=session,
                                redis=redis,
                                recovery_context=context,
                                holder_id=holder_id,
                            )
                            recovered += 1
                        finally:
                            await redis.aclose()

                    except Exception as exc:
                        errors.append({
                            "campaign_id": context.campaign_id,
                            "error": str(exc),
                        })

                return {
                    "status": "completed",
                    "stalled_count": len(stalled),
                    "recovered_count": recovered,
                    "errors": errors,
                }

        return _run_with_engine_reset(_run)

    except Exception as exc:
        if self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=60)
        return {"status": "error", "error": str(exc)}


@celery_app.task(
    bind=True,
    base=CampaignRecoveryTask,
    name=TASKS.campaign_recovery_manual,
    max_retries=3,
)
def recover_campaign_manual_task(
    self,
    campaign_id: int,
    workspace_id: int,
) -> dict:
    """
    Manually trigger recovery for a specific campaign.

    Use this for ad-hoc recovery when the periodic check is not sufficient.
    """
    from redis.asyncio import Redis

    async def _run():
        from app.db import AsyncSessionLocal
        from app.services.campaign_recovery_service import RecoveryContext

        async with AsyncSessionLocal() as session:
            from app.models.campaign import Campaign

            campaign = await session.get(Campaign, campaign_id)
            if not campaign:
                return {"status": "error", "error": "campaign_not_found"}

            # Create recovery context from campaign
            context = RecoveryContext(
                campaign_id=campaign.id,
                workspace_id=campaign.workspace_id,
                celery_task_id=campaign.celery_task_id,
                last_checkpoint_index=campaign.last_checkpoint_index or 0,
                total_recipients=0,  # Will be determined during recovery
                processed_recipients=campaign.success_count or 0,
                success_count=campaign.success_count or 0,
                failed_count=campaign.failed_count or 0,
                reason="manual_recovery_triggered",
            )

            await mark_campaign_recovering(session, campaign_id)
            await session.commit()

            redis = Redis.from_url(settings.redis_url, decode_responses=True)
            try:
                holder_id = f"manual-{self.request.id}"
                result = await recover_stalled_campaign(
                    session=session,
                    redis=redis,
                    recovery_context=context,
                    holder_id=holder_id,
                )
                return {"status": "recovered", **result}
            finally:
                await redis.aclose()

    return _run_with_engine_reset(_run)


# Celery Beat schedule for periodic recovery checks
def get_recovery_schedule() -> dict:
    """Get Celery Beat schedule for recovery tasks."""
    return {
        "campaign-recovery-check": {
            "task": TASKS.campaign_recovery_check,
            "schedule": 60.0,  # Every 60 seconds
            "options": {"queue": "default"},
        },
    }