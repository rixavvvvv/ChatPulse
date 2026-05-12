"""
Celery integration for structured logging.

Provides:
- Automatic trace_id propagation
- Task lifecycle logging
- Worker context enrichment
- Error handling with logging
"""

from __future__ import annotations

import os
import time
from functools import wraps
from typing import TYPE_CHECKING, Any, Callable

from celery import Task
from celery.signals import (
    task_prerun,
    task_postrun,
    task_failure,
    task_retry,
    worker_init,
    worker_shutdown,
)

from app.logging import (
    get_logger,
    get_trace_id,
    set_trace_id,
    set_task_id,
    set_task_name,
    set_queue_name,
    set_worker_id,
    set_workspace_id,
    log_context,
)

if TYPE_CHECKING:
    from celery import Celery


logger = get_logger(__name__)

# Global worker ID
_worker_id: str | None = None


def _get_worker_id() -> str:
    """Get or generate worker ID."""
    global _worker_id
    if _worker_id is None:
        _worker_id = os.environ.get("CELERY_WORKER_ID") or os.environ.get("HOSTNAME", "unknown")
    return _worker_id


# ─────────────────────────────────────────────────────────────────────────────
# Celery Signal Handlers
# ─────────────────────────────────────────────────────────────────────────────

@worker_init.connect
def on_worker_init(**kwargs) -> None:
    """Initialize logging when worker starts."""
    worker_id = _get_worker_id()
    set_worker_id(worker_id)

    log = get_logger("app.celery.worker")
    log.info(
        "worker.initialized",
        f"Worker initialized: {worker_id}",
        worker_id=worker_id,
    )


@worker_shutdown.connect
def on_worker_shutdown(**kwargs) -> None:
    """Log worker shutdown."""
    log = get_logger("app.celery.worker")
    log.info(
        "worker.shutdown",
        f"Worker shutting down: {_get_worker_id()}",
        worker_id=_get_worker_id(),
    )


@task_prerun.connect
def on_task_prerun(task_id: str, task: Task | None = None, **kwargs) -> None:
    """Set up logging context when task starts."""
    if task is None:
        return

    # Extract trace_id from task request
    trace_id = None
    workspace_id = None

    if hasattr(task, "request"):
        request = task.request
        trace_id = request.get("trace_id")
        workspace_id = request.get("workspace_id")

    # Set logging context
    trace_id = set_trace_id(trace_id)
    set_task_id(task_id)
    set_task_name(task.name or "unknown")
    set_queue_name(getattr(task, "queue", "") or "default")

    # Log task start
    log = get_logger("app.celery.task")
    log.info(
        f"{task.name}.started",
        f"Task started: {task.name}",
        task_name=task.name,
        task_id=task_id,
        trace_id=trace_id,
        workspace_id=workspace_id,
        metadata={
            "args_count": len(task.request.args) if hasattr(task.request, "args") else 0,
        },
    )


@task_postrun.connect
def on_task_postrun(task_id: str, task: Task | None = None, **kwargs) -> None:
    """Log task completion."""
    if task is None:
        return

    duration_ms = kwargs.get("duration", 0) * 1000 if kwargs.get("duration") else 0

    log = get_logger("app.celery.task")
    log.info(
        f"{task.name}.completed",
        f"Task completed: {task.name}",
        status="completed",
        task_name=task.name,
        task_id=task_id,
        duration_ms=round(duration_ms, 2),
    )


@task_failure.connect
def on_task_failure(
    task_id: str,
    exception: BaseException | None = None,
    task: Task | None = None,
    traceback: str | None = None,
    **kwargs,
) -> None:
    """Log task failure."""
    if task is None:
        return

    error_msg = str(exception) if exception else "Unknown error"

    log = get_logger("app.celery.task")
    log.error(
        f"{task.name}.failed",
        f"Task failed: {task.name}",
        status="failed",
        task_name=task.name,
        task_id=task_id,
        trace_id=get_trace_id(),
        metadata={
            "error": error_msg,
            "error_type": type(exception).__name__ if exception else None,
            "traceback": traceback,
        },
    )


@task_retry.connect
def on_task_retry(
    task_id: str,
    reason: Any,
    task: Task | None = None,
    **kwargs,
) -> None:
    """Log task retry."""
    if task is None:
        return

    retry_count = kwargs.get("delivery_info", {}).get("redelivered", False)

    log = get_logger("app.celery.task")
    log.warning(
        f"{task.name}.retry",
        f"Task retrying: {task.name}",
        status="retrying",
        task_name=task.name,
        task_id=task_id,
        trace_id=get_trace_id(),
        metadata={
            "reason": str(reason),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Logging Decorator
# ─────────────────────────────────────────────────────────────────────────────

def with_logging(func: Callable | None = None, *, task_name: str | None = None) -> Callable:
    """
    Decorator to add structured logging to Celery tasks.

    Usage:
        @with_logging
        @celery_app.task
        def send_message(...):
            ...

        @with_logging(task_name="custom.name")
        @celery_app.task
        def another_task(...):
            ...
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            task_instance = args[0] if args else None
            task_id = getattr(task_instance, "request", None).id if task_instance else "unknown"
            name = task_name or getattr(task_instance, "name", f.__name__)

            start_time = time.perf_counter()
            trace_id = get_trace_id()

            try:
                result = f(*args, **kwargs)
                duration_ms = (time.perf_counter() - start_time) * 1000

                log = get_logger("app.celery.decorator")
                log.info(
                    f"{name}.completed",
                    f"Task completed: {name}",
                    status="completed",
                    task_name=name,
                    task_id=task_id,
                    trace_id=trace_id,
                    duration_ms=round(duration_ms, 2),
                )
                return result

            except Exception as exc:
                duration_ms = (time.perf_counter() - start_time) * 1000

                log = get_logger("app.celery.decorator")
                log.error(
                    f"{name}.failed",
                    f"Task failed: {name}",
                    status="failed",
                    task_name=name,
                    task_id=task_id,
                    trace_id=trace_id,
                    duration_ms=round(duration_ms, 2),
                    metadata={
                        "error": str(exc),
                        "error_type": type(exc).__name__,
                    },
                )
                raise

        return wrapper

    if func:
        return decorator(func)
    return decorator


def with_task_context(task_name: str | None = None) -> Callable:
    """
    Decorator to set up task logging context.

    Usage:
        @with_task_context("campaign.send")
        def send_campaign_task(self, workspace_id, campaign_id):
            logger = get_logger(__name__)
            logger.info("sending", "Sending campaign")
    """
    def decorator(f: Callable) -> Callable:
        @wraps(f)
        def wrapper(*args, **kwargs):
            task = args[0] if args else None

            if task and hasattr(task, "request"):
                request = task.request
                set_task_id(request.id)
                set_task_name(task_name or task.name or f.__name__)

                # Propagate trace context
                trace_id = request.get("trace_id") or get_trace_id()
                set_trace_id(trace_id)

                # Set workspace context if available
                workspace_id = request.get("workspace_id")
                if workspace_id:
                    set_workspace_id(workspace_id)

            return f(*args, **kwargs)

        return wrapper
    return decorator


# ─────────────────────────────────────────────────────────────────────────────
# Context Propagation
# ─────────────────────────────────────────────────────────────────────────────

class LogContextPropagatingTask(Task):
    """
    Base Celery task that propagates logging context.

    Automatically:
    - Sets trace_id from request
    - Sets task_id and task_name
    - Sets workspace_id if present
    - Cleans up context after task completes
    """

    abstract = True

    def __call__(self, *args, **kwargs):
        """Set up logging context before task execution."""
        # Extract context from request
        request = getattr(self, "request", None)
        if request:
            set_task_id(request.id)
            set_task_name(self.name or "unknown")

            # Propagate trace
            trace_id = request.get("trace_id")
            if trace_id:
                set_trace_id(trace_id)

            # Set workspace context
            workspace_id = request.get("workspace_id")
            if workspace_id:
                set_workspace_id(workspace_id)

        return super().__call__(*args, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Helper Functions
# ─────────────────────────────────────────────────────────────────────────────

def propagate_trace_to_task(kwargs: dict, trace_id: str | None = None) -> dict:
    """
    Add trace_id to task kwargs for propagation to workers.

    Usage:
        task.delay(
            **propagate_trace_to_task({"workspace_id": 123}, get_trace_id()),
            campaign_id=456
        )
    """
    if trace_id is None:
        trace_id = get_trace_id()

    if trace_id:
        kwargs["trace_id"] = trace_id

    return kwargs


def create_task_logger(name: str) -> Any:
    """
    Create a logger with automatic task context.

    Usage:
        logger = create_task_logger(__name__)
        logger.info("message.sent", "Message sent")
    """
    return get_logger(name)