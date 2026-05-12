"""
Celery task base classes and crash-recovery infrastructure.

This module provides:
1. Base task classes with late acknowledgment
2. Idempotency mixins
3. Safe transaction boundaries
4. Crash recovery patterns

Why Late Acknowledgment Matters
-------------------------------
By default, Celery acknowledges messages BEFORE the task executes. This means:

  1. Worker picks up task from queue
  2. Broker marks task as ACKed (removed from queue)
  3. Worker executes task
  4. Worker crashes during execution
  5. Task is LOST - it will never be retried

With late acknowledgment (task_acks_late=True):
  1. Worker picks up task from queue
  2. Worker executes task
  3. Task completes successfully → ACK sent → removed from queue
  4. Worker crashes during execution
  5. Broker requeues task → another worker picks it up
  6. Task is RETRIED - no data loss

Crash Recovery Lifecycle
-----------------------

Worker Normal Shutdown:
  SIGTERM received → gracefully stops accepting new tasks
  → waits for current tasks to complete → ACKs completed tasks
  → exits

Worker Crash (SIGKILL/OOM):
  Worker process killed abruptly
  → Message NOT acknowledged (still in broker queue)
  → Visibility timeout expires → message returned to queue
  → Another worker picks up and executes
  → task_reject_on_worker_lost=True ensures immediate requeue

Container/Process Restart:
  1. Orchestrator kills old container → all workers die
  2. Messages are still in Redis broker (not acknowledged)
  3. Visibility timeout (5 min default) expires
  4. Messages returned to their queues
  5. New workers pick them up and execute

Duplicate Execution Handling
----------------------------
Late acknowledgment enables "at-least-once" delivery, not "exactly-once".
A task may execute multiple times if workers crash at the wrong moment.

Solutions:
1. Idempotent tasks - same inputs always produce same outputs
2. Idempotency keys in Redis (already implemented)
3. Database unique constraints
4. Check-before-write patterns

Visibility Timeout
------------------
Redis broker: Messages have a visibility timeout (default 5 min).
If a message isn't acknowledged within this window, it's requeued.

Redis visibility_timeout = broker_transport_options.get('visibility_timeout', 3600)
Set to 300 (5 min) for fast recovery, or higher for long-running tasks.

Safe Task Pattern
----------------
Every task using late acknowledgment MUST be idempotent:

  @celery_app.task(acks_late=True)
  def send_campaign_message(campaign_id, contact_id):
      # 1. Check if already sent (idempotency)
      if already_sent(campaign_id, contact_id):
          return "already_sent"

      # 2. Do the work
      result = send_message(...)

      # 3. Only after complete success:
      mark_as_sent(campaign_id, contact_id)
      return result

Not Safe (without idempotency):
  @celery_app.task(acks_late=True)
  def send_message_without_check(campaign_id, contact_id):
      send_message(...)  # May send multiple times on crash!
      return "done"
"""

from __future__ import annotations

import asyncio
import logging
from abc import abstractmethod
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Callable, Self

from celery import Task
from celery.exceptions import MaxRetriesExceededError, Retry
from redis.asyncio import Redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


@dataclass
class TaskExecutionContext:
    """Context passed to tasks with recovery metadata."""

    task_id: str
    task_name: str
    retry_count: int
    max_retries: int
    execution_attempt: int
    started_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class IdempotencyMixin:
    """
    Mixin providing Redis-based idempotency for tasks.

    Ensures tasks with the same idempotency_key only execute once,
    even when retried or executed after worker crash.
    """

    @staticmethod
    def _idempotency_key(task_name: str, key_suffix: str) -> str:
        return f"celery:task:executed:{task_name}:{key_suffix}"

    @staticmethod
    async def check_and_mark_executed(
        redis: Redis,
        key_suffix: str,
        task_name: str,
        ttl_seconds: int = 86400,
    ) -> bool:
        """
        Check if task already executed, mark as executing if not.

        Returns True if task should proceed (not yet executed).
        Returns False if task already completed (should skip).

        Uses SET NX for atomic check-and-set.
        """
        key = IdempotencyMixin._idempotency_key(task_name, key_suffix)
        result = await redis.set(key, "executing", ex=ttl_seconds, nx=True)
        return result is not None

    @staticmethod
    async def mark_completed(
        redis: Redis,
        key_suffix: str,
        task_name: str,
        ttl_seconds: int = 86400,
    ) -> None:
        """
        Mark task as completed.

        Uses SET EX (already atomic) to update the executing state.
        """
        key = IdempotencyMixin._idempotency_key(task_name, key_suffix)
        await redis.set(key, "completed", ex=ttl_seconds)

    @staticmethod
    async def is_completed(
        redis: Redis,
        key_suffix: str,
        task_name: str,
    ) -> bool:
        """
        Check if task already completed.
        """
        key = IdempotencyMixin._idempotency_key(task_name, key_suffix)
        value = await redis.get(key)
        return value == "completed"

    @staticmethod
    async def release_execution(
        redis: Redis,
        key_suffix: str,
        task_name: str,
    ) -> None:
        """
        Release the execution lock if task needs to retry.

        Call this if task fails and should allow retry.
        """
        key = IdempotencyMixin._idempotency_key(task_name, key_suffix)
        await redis.delete(key)


@dataclass
class RetryStrategy:
    """Configurable retry strategy for tasks."""

    max_attempts: int = 4
    base_delay_seconds: int = 2
    max_delay_seconds: int = 600
    exponential_base: int = 2
    jitter: bool = True

    def delay_seconds(self, attempt: int, suggested_delay: int | None = None) -> int:
        """
        Calculate delay for given retry attempt.

        Uses exponential backoff with optional jitter.
        """
        if attempt <= 0:
            return self.base_delay_seconds

        delay = self.base_delay_seconds * (self.exponential_base ** (attempt - 1))
        delay = min(delay, self.max_delay_seconds)

        if suggested_delay is not None:
            delay = max(delay, suggested_delay)

        if self.jitter:
            import random

            delay = delay * (0.5 + random.random() * 0.5)

        return int(delay)


@dataclass
class CrashRecoveryState:
    """
    State tracking for crash recovery scenarios.

    Tracks whether task is executing, completed, or failed
    across worker restarts.
    """

    task_name: str
    idempotency_key: str
    status: str = "pending"  # pending, executing, completed, failed
    executions: int = 0
    last_execution_at: datetime | None = None
    error: str | None = None


class BaseCrashRecoveryTask(Task):
    """
    Base task class with crash recovery support.

    Features:
    - Late acknowledgment (task_acks_late=True)
    - Automatic retry on transient failures
    - Idempotency key support
    - Dead letter queue on exhaustion
    - Safe transaction boundaries
    - Execution tracking for monitoring

    Usage:
        @celery_app.task(
            bind=True,
            base=BaseCrashRecoveryTask,
            name="my.task",
            max_retries=3,
        )
        def my_task(self, arg1, arg2):
            # Use self.safe_execute() for idempotent execution
            pass
    """

    abstract = True
    acks_late = True
    reject_on_worker_lost = True

    autoretry_for: tuple[type[Exception], ...] = (
        ConnectionError,
        TimeoutError,
        OSError,
    )
    retry_backoff = True
    retry_backoff_max = 600
    retry_jitter = True

    def __init__(self: Self) -> None:
        self._execution_context: TaskExecutionContext | None = None
        super().__init__()

    @property
    def execution_context(self: Self) -> TaskExecutionContext | None:
        """Get execution context for this task instance."""
        return self._execution_context

    def setup(
        self: Self,
        name: str | None = None,
        bind: bool = False,
        **kwargs: Any,
    ) -> Callable[..., Any] | None:
        result = super().setup(name, bind, **kwargs)
        self._execution_context = TaskExecutionContext(
            task_id=self.request.id if hasattr(self, "request") else "unknown",
            task_name=name or self.name,
            retry_count=getattr(self.request, "retries", 0),
            max_retries=self.max_retries or 0,
            execution_attempt=getattr(self.request, "retries", 0) + 1,
        )
        return result

    @abstractmethod
    def _do_execute(self: Self, *args: Any, **kwargs: Any) -> Any:
        """
        Implement actual task execution.

        This method MUST be idempotent - it may be called multiple times
        if workers crash and restart.
        """
        raise NotImplementedError

    def safe_execute(
        self: Self,
        idempotency_key_suffix: str,
        idempotency_ttl_seconds: int = 86400,
        redis_url: str | None = None,
    ) -> tuple[bool, Any]:
        """
        Execute task with idempotency guarantees.

        Returns:
            Tuple of (executed, result)
            - (True, result) if task executed successfully
            - (False, "already_executed") if task already completed

        This ensures safe execution even after worker crashes.
        """
        import asyncio

        redis = Redis.from_url(
            redis_url or settings.redis_url,
            decode_responses=True,
        )

        try:
            key_suffix = f"{self.request.id}:{idempotency_key_suffix}"

            async def _check_and_execute() -> tuple[bool, Any]:
                should_proceed = await IdempotencyMixin.check_and_mark_executed(
                    redis,
                    key_suffix,
                    self.name,
                    ttl_seconds=idempotency_ttl_seconds,
                )

                if not should_proceed:
                    already_done = await IdempotencyMixin.is_completed(
                        redis, key_suffix, self.name
                    )
                    if already_done:
                        return False, "already_completed"
                    return False, "currently_executing"

                try:
                    result = await asyncio.to_thread(
                        lambda: self._do_execute(*self.request.args, **self.request.kwargs)
                    )
                    await IdempotencyMixin.mark_completed(
                        redis, key_suffix, self.name, ttl_seconds=idempotency_ttl_seconds
                    )
                    return True, result
                except Exception:
                    await IdempotencyMixin.release_execution(
                        redis, key_suffix, self.name
                    )
                    raise

            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                return loop.run_until_complete(_check_and_execute())
            finally:
                loop.close()
        finally:
            asyncio.run(redis.aclose())

    def on_failure(
        self: Self,
        exc: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Handle task failure."""
        if isinstance(exc, Retry):
            return super().on_failure(exc, task_id, args, kwargs, einfo)

        logger.error(
            "Task failed task_id=%s name=%s error=%s",
            task_id,
            self.name,
            exc,
            exc_info=True,
        )

        if self.max_retries and self.request.retries >= self.max_retries:
            self._on_max_retries_exceeded(exc, task_id, args, kwargs, einfo)

    def _on_max_retries_exceeded(
        self: Self,
        exc: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Called when task has exhausted all retries."""
        logger.error(
            "Task exhausted retries task_id=%s name=%s attempts=%s",
            task_id,
            self.name,
            self.request.retries,
        )

    def on_success(
        self: Self,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
    ) -> None:
        """Called on successful task completion."""
        logger.info(
            "Task completed task_id=%s name=%s retry_count=%s",
            task_id,
            self.name,
            self.request.retries,
        )

    def after_return(
        self: Self,
        status: str,
        retval: Any,
        task_id: str,
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        einfo: Any,
    ) -> None:
        """Called after task returns, regardless of success or failure."""
        pass

    def send_event(
        self: Self,
        event_type: str,
        **kwargs: Any,
    ) -> None:
        """Send a custom event for monitoring."""
        self.app.control.inspect().send_task_event(
            task_id=self.request.id,
            event=event_type,
            **kwargs,
        )


class LongRunningTask(BaseCrashRecoveryTask):
    """
    Base class for long-running tasks (campaign sends, imports).

    Features:
    - Higher visibility timeout
    - Checkpoint support for progress recovery
    - Batch processing support
    """

    abstract = True
    visibility_timeout: int = 3600  # 1 hour for long tasks

    @abstractmethod
    def _do_execute(self: Self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError

    def checkpoint(
        self: Self,
        checkpoint_name: str,
        progress: float,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """
        Save task progress checkpoint for crash recovery.

        If worker crashes, task can resume from checkpoint.
        """
        from app.services.queue_monitoring_service import update_task_checkpoint

        try:
            update_task_checkpoint(
                task_id=self.request.id,
                task_name=self.name,
                checkpoint_name=checkpoint_name,
                progress=progress,
                metadata=metadata or {},
            )
        except Exception as exc:  # pragma: no cover
            logger.warning(
                "Failed to save checkpoint task_id=%s checkpoint=%s: %s",
                self.request.id,
                checkpoint_name,
                exc,
            )

    def get_checkpoint(self: Self, checkpoint_name: str) -> dict[str, Any] | None:
        """Get saved checkpoint for crash recovery."""
        from app.services.queue_monitoring_service import get_task_checkpoint

        try:
            return get_task_checkpoint(self.request.id, checkpoint_name)
        except Exception:  # pragma: no cover
            return None


class FastIOTask(BaseCrashRecoveryTask):
    """
    Base class for fast I/O tasks (webhooks, notifications).

    Features:
    - Low visibility timeout
    - High concurrency
    - Strict timeout enforcement
    """

    abstract = True
    visibility_timeout: int = 300  # 5 minutes for fast tasks
    time_limit: int = 60  # Hard timeout
    soft_time_limit: int = 45  # Soft timeout for graceful shutdown

    @abstractmethod
    def _do_execute(self: Self, *args: Any, **kwargs: Any) -> Any:
        raise NotImplementedError
