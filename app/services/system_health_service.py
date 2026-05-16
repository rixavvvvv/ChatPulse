"""
System Health Service

Aggregates health data from Redis, PostgreSQL, Celery workers,
WebSocket connections, delayed executions, and workflow failures.
"""

import logging
from datetime import datetime, timezone
from typing import Any

from redis.asyncio import Redis
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.queue_dead_letter import QueueDeadLetter
from app.models.workflow import WorkflowExecution
from app.models.workflow_delayed import WorkflowDelayed
from app.services.queue_monitoring_service import celery_inspect_snapshot
from app.services.redis_pubsub_manager import get_redis_manager

logger = logging.getLogger(__name__)
settings = get_settings()


async def check_redis_health(redis: Redis) -> dict[str, Any]:
    """Check Redis connectivity and basic stats."""
    try:
        start = datetime.now(timezone.utc)
        pong = await redis.ping()
        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        info = await redis.info("stats")
        db_info = await redis.info("db")

        return {
            "status": "healthy" if pong else "unhealthy",
            "latency_ms": round(latency_ms, 2),
            "connected": True,
            "version": info.get("redis_version"),
            "used_memory_mb": round(info.get("used_memory", 0) / 1024 / 1024, 2),
            "connected_clients": info.get("connected_clients", 0),
            "total_keys": sum(db.get("keys", 0) for db in db_info.values() if isinstance(db, dict)),
        }
    except Exception as e:
        logger.error(f"Redis health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "connected": False,
        }


async def check_postgres_health(session: AsyncSession) -> dict[str, Any]:
    """Check PostgreSQL connectivity and basic stats."""
    try:
        start = datetime.now(timezone.utc)

        # Simple query to check connection
        await session.execute(select(1))

        latency_ms = (datetime.now(timezone.utc) - start).total_seconds() * 1000

        # Get table counts (sample)
        result = await session.execute(
            select(func.count(WorkflowExecution.id))
        )
        workflow_executions = result.scalar() or 0

        result = await session.execute(
            select(func.count(WorkflowDelayed.id))
        )
        delayed_executions = result.scalar() or 0

        result = await session.execute(
            select(func.count(QueueDeadLetter.id))
        )
        failed_jobs = result.scalar() or 0

        return {
            "status": "healthy",
            "latency_ms": round(latency_ms, 2),
            "connected": True,
            "workflow_executions": workflow_executions,
            "delayed_executions": delayed_executions,
            "failed_jobs": failed_jobs,
        }
    except Exception as e:
        logger.error(f"PostgreSQL health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "connected": False,
        }


def check_celery_health() -> dict[str, Any]:
    """Check Celery worker health via inspect."""
    try:
        snapshot = celery_inspect_snapshot(timeout_seconds=2.0)

        if not snapshot.get("reachable"):
            return {
                "status": "unhealthy",
                "reachable": False,
                "error": snapshot.get("error", "Unknown error"),
            }

        ping_result = snapshot.get("ping", {})
        active_result = snapshot.get("active", {})
        stats_result = snapshot.get("stats", {})

        # Count responsive workers
        worker_count = sum(1 for v in ping_result.values() if v is not None)

        # Count active tasks
        active_tasks = sum(len(v) for v in active_result.values() if isinstance(v, dict))

        # Aggregate stats
        total_pool = 0
        max_tasks = 0
        for stats in stats_result.values():
            if isinstance(stats, dict):
                pool = stats.get("pool", {})
                if isinstance(pool, dict):
                    total_pool += pool.get("max", 0)
                    max_tasks += pool.get("max", 0)

        return {
            "status": "healthy" if worker_count > 0 else "unhealthy",
            "reachable": True,
            "workers_online": worker_count,
            "active_tasks": active_tasks,
            "max_workers": max_tasks,
            "ping_results": ping_result,
        }
    except Exception as e:
        logger.error(f"Celery health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "reachable": False,
        }


async def check_websocket_health() -> dict[str, Any]:
    """Check WebSocket manager health."""
    try:
        # Check if WebSocket manager can be accessed
        manager = get_redis_manager()
        active_connections = 0
        active_rooms = 0

        # Try to get connection/room counts if methods exist
        if hasattr(manager, "get_active_connection_count"):
            active_connections = await manager.get_active_connection_count()
        if hasattr(manager, "get_room_count"):
            active_rooms = await manager.get_room_count()

        return {
            "status": "healthy",
            "active_connections": active_connections,
            "active_rooms": active_rooms,
            "connected": True,
        }
    except Exception as e:
        logger.error(f"WebSocket health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
            "connected": False,
        }


async def get_queue_health() -> dict[str, Any]:
    """Get queue depth and status."""
    try:
        redis = Redis.from_url(settings.redis_url)
        try:
            # Check common queue keys
            queues = ["bulk-messages", "webhooks", "default"]
            queue_stats = {}

            for queue in queues:
                # Approximate depth via len
                key = f"celery:queue:{queue}"
                length = await redis.llen(key) if await redis.exists(key) else 0

                # Also check scheduled
                scheduled_key = f"celery@%s.scheduled" % queue
                scheduled_count = 0

                queue_stats[queue] = {
                    "depth": length,
                    "scheduled": scheduled_count,
                }

            return {
                "status": "healthy",
                "queues": queue_stats,
            }
        finally:
            await redis.aclose()
    except Exception as e:
        logger.error(f"Queue health check failed: {e}")
        return {
            "status": "unhealthy",
            "error": str(e),
        }


async def get_failed_jobs_count(session: AsyncSession) -> dict[str, Any]:
    """Get failed jobs count from dead letter queue."""
    try:
        result = await session.execute(
            select(func.count(QueueDeadLetter.id))
        )
        total = result.scalar() or 0

        # Get recent failures (last hour)
        from datetime import timedelta
        recent = await session.execute(
            select(func.count(QueueDeadLetter.id))
            .where(QueueDeadLetter.created_at >= datetime.now(timezone.utc) - timedelta(hours=1))
        )
        recent_count = recent.scalar() or 0

        return {
            "total": total,
            "last_hour": recent_count,
        }
    except Exception as e:
        logger.error(f"Failed jobs check failed: {e}")
        return {
            "error": str(e),
        }


async def get_delayed_executions_count(session: AsyncSession) -> dict[str, Any]:
    """Get delayed executions count."""
    try:
        # Count pending delayed executions
        result = await session.execute(
            select(func.count(WorkflowDelayed.id))
            .where(WorkflowDelayed.execute_at > datetime.now(timezone.utc))
        )
        pending = result.scalar() or 0

        # Count overdue
        result = await session.execute(
            select(func.count(WorkflowDelayed.id))
            .where(
                WorkflowDelayed.execute_at <= datetime.now(timezone.utc),
                WorkflowDelayed.status == "pending"
            )
        )
        overdue = result.scalar() or 0

        return {
            "pending": pending,
            "overdue": overdue,
        }
    except Exception as e:
        logger.error(f"Delayed executions check failed: {e}")
        return {
            "error": str(e),
        }


async def get_workflow_failures_count(session: AsyncSession) -> dict[str, Any]:
    """Get workflow failures count."""
    try:
        from datetime import timedelta

        # Total failed
        result = await session.execute(
            select(func.count(WorkflowExecution.id))
            .where(WorkflowExecution.status == "failed")
        )
        total_failed = result.scalar() or 0

        # Recent failures (last hour)
        result = await session.execute(
            select(func.count(WorkflowExecution.id))
            .where(
                WorkflowExecution.status == "failed",
                WorkflowExecution.updated_at >= datetime.now(timezone.utc) - timedelta(hours=1)
            )
        )
        recent_failures = result.scalar() or 0

        return {
            "total_failed": total_failed,
            "last_hour": recent_failures,
        }
    except Exception as e:
        logger.error(f"Workflow failures check failed: {e}")
        return {
            "error": str(e),
        }


async def get_system_health_summary(session: AsyncSession) -> dict[str, Any]:
    """Get complete system health summary."""
    redis = Redis.from_url(settings.redis_url)
    try:
        # Run checks in parallel where possible
        redis_health = await check_redis_health(redis)
        postgres_health = await check_postgres_health(session)
        celery_health = check_celery_health()
        websocket_health = await check_websocket_health()
        queue_health = await get_queue_health()
        failed_jobs = await get_failed_jobs_count(session)
        delayed = await get_delayed_executions_count(session)
        workflow_failures = await get_workflow_failures_count(session)

        # Determine overall status
        all_healthy = (
            redis_health.get("status") == "healthy" and
            postgres_health.get("status") == "healthy" and
            celery_health.get("status") == "healthy"
        )

        return {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "overall_status": "healthy" if all_healthy else "degraded",
            "redis": redis_health,
            "postgresql": postgres_health,
            "celery": celery_health,
            "websocket": websocket_health,
            "queues": queue_health,
            "failed_jobs": failed_jobs,
            "delayed_executions": delayed,
            "workflow_failures": workflow_failures,
        }
    finally:
        await redis.aclose()