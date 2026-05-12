from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from redis.asyncio import Redis

from app.core.config import get_settings
from app.queue.celery_app import celery_app

logger = logging.getLogger(__name__)
settings = get_settings()


def celery_inspect_snapshot(timeout_seconds: float = 1.0) -> dict[str, Any]:
    """Best-effort broker/worker snapshot for ops dashboards (requires reachable workers)."""
    try:
        inspector = celery_app.control.inspect(timeout=timeout_seconds)
    except Exception as exc:  # pragma: no cover
        logger.warning("Celery inspect init failed: %s", exc)
        return {"reachable": False, "error": str(exc)}

    if inspector is None:
        return {"reachable": False, "error": "no inspector"}

    snapshot: dict[str, Any] = {"reachable": True}
    for name, fn in (
        ("ping", inspector.ping),
        ("active", inspector.active),
        ("reserved", inspector.reserved),
        ("scheduled", inspector.scheduled),
        ("stats", inspector.stats),
    ):
        try:
            snapshot[name] = fn()
        except Exception as exc:  # pragma: no cover
            snapshot[name] = {"error": str(exc)}
    return snapshot


_CHECKPOINT_KEY_PREFIX = "celery:checkpoint"


def _checkpoint_key(task_id: str, checkpoint_name: str) -> str:
    return f"{_CHECKPOINT_KEY_PREFIX}:{task_id}:{checkpoint_name}"


def update_task_checkpoint(
    task_id: str,
    task_name: str,
    checkpoint_name: str,
    progress: float,
    metadata: dict[str, Any] | None = None,
    ttl_seconds: int = 86400,
) -> None:
    """
    Save task progress checkpoint for crash recovery.

    If a worker crashes during a long-running task,
    a new worker can read the checkpoint and resume.

    Args:
        task_id: Celery task ID
        task_name: Name of the task
        checkpoint_name: Identifier for this checkpoint
        progress: Progress percentage (0.0 to 1.0)
        metadata: Additional checkpoint data
        ttl_seconds: How long to keep checkpoint (default 24h)
    """
    import asyncio

    key = _checkpoint_key(task_id, checkpoint_name)
    data = {
        "task_id": task_id,
        "task_name": task_name,
        "checkpoint_name": checkpoint_name,
        "progress": progress,
        "metadata": metadata or {},
        "updated_at": datetime.now(tz=UTC).isoformat(),
    }

    async def _update() -> None:
        redis = Redis.from_url(settings.redis_url)
        try:
            await redis.set(key, json.dumps(data), ex=ttl_seconds)
        finally:
            await redis.aclose()

    asyncio.run(_update())


def get_task_checkpoint(task_id: str, checkpoint_name: str) -> dict[str, Any] | None:
    """
    Get saved checkpoint for crash recovery.

    Returns None if no checkpoint exists.
    """
    import asyncio

    key = _checkpoint_key(task_id, checkpoint_name)

    async def _get() -> dict[str, Any] | None:
        redis = Redis.from_url(settings.redis_url)
        try:
            data = await redis.get(key)
            if data:
                return json.loads(data)
            return None
        finally:
            await redis.aclose()

    return asyncio.run(_get())


def clear_task_checkpoints(task_id: str) -> None:
    """Clear all checkpoints for a task (on completion)."""
    import asyncio

    pattern = f"{_CHECKPOINT_KEY_PREFIX}:{task_id}:*"

    async def _clear() -> None:
        redis = Redis.from_url(settings.redis_url)
        try:
            cursor = 0
            while True:
                cursor, keys = await redis.scan(cursor, match=pattern, count=100)
                if keys:
                    await redis.delete(*keys)
                if cursor == 0:
                    break
        finally:
            await redis.aclose()

    asyncio.run(_clear())


def get_task_executions(task_id: str) -> int:
    """Get the number of times a task has been attempted."""
    import asyncio

    key = f"celery:task:executions:{task_id}"

    async def _get() -> int:
        redis = Redis.from_url(settings.redis_url)
        try:
            count = await redis.get(key)
            return int(count) if count else 0
        finally:
            await redis.aclose()

    return asyncio.run(_get())


def increment_task_execution(task_id: str, ttl_seconds: int = 86400) -> None:
    """Track task execution count for monitoring."""
    import asyncio

    key = f"celery:task:executions:{task_id}"

    async def _increment() -> None:
        redis = Redis.from_url(settings.redis_url)
        try:
            await redis.incr(key)
            await redis.expire(key, ttl_seconds)
        finally:
            await redis.aclose()

    asyncio.run(_increment())
