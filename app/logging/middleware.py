"""
FastAPI middleware for structured logging.

Provides:
- Request/response logging
- Trace ID propagation
- Request ID generation
- Timing information
"""

from __future__ import annotations

import time
from typing import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from app.logging import get_logger, get_trace_id, set_trace_id, get_request_id, set_request_id


logger = get_logger(__name__)


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for structured request/response logging.

    Features:
    - Generates or extracts trace_id
    - Logs request start/end
    - Captures timing, status, and metadata
    - Adds correlation headers to response
    """

    def __init__(
        self,
        app: ASGIApp,
        log_request_body: bool = False,
        log_response_body: bool = False,
        log_headers: bool = False,
        exclude_paths: list[str] | None = None,
    ):
        super().__init__(app)
        self.log_request_body = log_request_body
        self.log_response_body = log_response_body
        self.log_headers = log_headers
        self.exclude_paths = exclude_paths or ["/health", "/metrics", "/favicon.ico"]

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        """Process request with logging."""
        # Check if path should be excluded
        if any(request.url.path.startswith(path) for path in self.exclude_paths):
            return await call_next(request)

        # Extract or generate trace_id
        trace_id = request.headers.get("X-Trace-ID") or request.headers.get("x-trace-id")
        trace_id = set_trace_id(trace_id)

        # Generate request ID
        request_id = get_request_id() or str(time.time_ns())
        set_request_id(request_id)

        # Record start time
        start_time = time.perf_counter()

        # Extract client IP
        client_ip = self._get_client_ip(request)

        # Log request start
        self._log_request_start(request, trace_id, client_ip)

        # Process request
        response = await call_next(request)

        # Calculate duration
        duration_ms = (time.perf_counter() - start_time) * 1000

        # Log request completion
        self._log_request_end(request, response, duration_ms, trace_id)

        # Add correlation headers to response
        response.headers["X-Trace-ID"] = trace_id
        response.headers["X-Request-ID"] = request_id

        return response

    def _get_client_ip(self, request: Request) -> str:
        """Extract client IP from request."""
        # Check for forwarded headers (behind proxy)
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            return forwarded.split(",")[0].strip()
        real_ip = request.headers.get("X-Real-IP")
        if real_ip:
            return real_ip
        if request.client:
            return request.client.host
        return "unknown"

    def _log_request_start(
        self, request: Request, trace_id: str, client_ip: str
    ) -> None:
        """Log incoming request."""
        log = get_logger("app.middleware.request")

        metadata = {
            "method": request.method,
            "path": request.url.path,
            "query": str(request.query_params) if request.query_params else None,
            "client_ip": client_ip,
            "user_agent": request.headers.get("User-Agent"),
        }

        if self.log_headers:
            metadata["headers"] = {
                k: v for k, v in request.headers.items()
                if not k.lower().startswith(("authorization", "cookie", "x-api-key"))
            }

        log.info(
            "http.request.started",
            f"{request.method} {request.url.path}",
            trace_id=trace_id,
            request_id=get_request_id(),
            metadata=metadata,
        )

    def _log_request_end(
        self,
        request: Request,
        response: Response,
        duration_ms: float,
        trace_id: str,
    ) -> None:
        """Log request completion."""
        log = get_logger("app.middleware.request")

        status = "success" if response.status_code < 400 else "failed"
        if response.status_code >= 500:
            status = "error"

        event = "http.request.completed"
        if response.status_code >= 500:
            event = "http.request.error"
        elif response.status_code >= 400:
            event = "http.request.client_error"

        log.info(
            event,
            f"{request.method} {request.url.path} -> {response.status_code}",
            status=status,
            duration_ms=round(duration_ms, 2),
            trace_id=trace_id,
            request_id=get_request_id(),
            metadata={
                "method": request.method,
                "path": request.url.path,
                "status_code": response.status_code,
            },
        )


# ─────────────────────────────────────────────────────────────────────────────
# Webhook-Specific Logging
# ─────────────────────────────────────────────────────────────────────────────

def log_webhook_received(
    source: str,
    event_type: str,
    payload_size: int,
    headers: dict | None = None,
    workspace_id: int | None = None,
) -> None:
    """Log webhook receipt."""
    log = get_logger("app.webhook")

    log.info(
        "webhook.received",
        f"Webhook received from {source}: {event_type}",
        workspace_id=workspace_id,
        metadata={
            "source": source,
            "event_type": event_type,
            "payload_size": payload_size,
            "headers": headers,
        } if headers else {
            "source": source,
            "event_type": event_type,
            "payload_size": payload_size,
        },
    )


def log_webhook_processed(
    source: str,
    event_type: str,
    duration_ms: float,
    status: str,
    workspace_id: int | None = None,
    error: str | None = None,
) -> None:
    """Log webhook processing completion."""
    log = get_logger("app.webhook")

    event = "webhook.processed.success" if status == "success" else "webhook.processed.failed"

    log.info(
        event,
        f"Webhook processed from {source}: {event_type}",
        status=status,
        duration_ms=round(duration_ms, 2),
        workspace_id=workspace_id,
        metadata={
            "source": source,
            "event_type": event_type,
            "error": error,
        } if error else {
            "source": source,
            "event_type": event_type,
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Celery Task Logging Utilities
# ─────────────────────────────────────────────────────────────────────────────

def log_task_started(
    task_name: str,
    task_id: str,
    queue_name: str,
    args: tuple | None = None,
    kwargs: dict | None = None,
    workspace_id: int | None = None,
) -> None:
    """Log Celery task start."""
    log = get_logger("app.celery")

    log.info(
        f"{task_name}.started",
        f"Task started: {task_name}",
        task_name=task_name,
        task_id=task_id,
        queue_name=queue_name,
        workspace_id=workspace_id,
        metadata={
            "args": args,
            "kwargs": kwargs,
        } if args or kwargs else {},
    )


def log_task_completed(
    task_name: str,
    task_id: str,
    duration_ms: float,
    result: dict | None = None,
    workspace_id: int | None = None,
) -> None:
    """Log Celery task completion."""
    log = get_logger("app.celery")

    log.info(
        f"{task_name}.completed",
        f"Task completed: {task_name}",
        status="completed",
        duration_ms=round(duration_ms, 2),
        task_name=task_name,
        task_id=task_id,
        workspace_id=workspace_id,
        metadata={"result": result} if result else {},
    )


def log_task_failed(
    task_name: str,
    task_id: str,
    duration_ms: float,
    error: str,
    traceback: str | None = None,
    workspace_id: int | None = None,
) -> None:
    """Log Celery task failure."""
    log = get_logger("app.celery")

    log.error(
        f"{task_name}.failed",
        f"Task failed: {task_name}",
        status="failed",
        duration_ms=round(duration_ms, 2),
        task_name=task_name,
        task_id=task_id,
        workspace_id=workspace_id,
        metadata={
            "error": error,
            "traceback": traceback,
        } if traceback else {"error": error},
    )


def log_task_retry(
    task_name: str,
    task_id: str,
    attempt: int,
    max_attempts: int,
    delay: int | None = None,
    workspace_id: int | None = None,
) -> None:
    """Log Celery task retry."""
    log = get_logger("app.celery")

    log.warning(
        f"{task_name}.retry",
        f"Task retry: {task_name} (attempt {attempt}/{max_attempts})",
        status="retrying",
        workspace_id=workspace_id,
        metadata={
            "attempt": attempt,
            "max_attempts": max_attempts,
            "delay_seconds": delay,
        },
    )