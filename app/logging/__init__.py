"""
Centralized structured logging infrastructure for ChatPulse.

Provides:
- Standardized JSON log format
- Trace ID propagation
- Context enrichment
- Safe PII redaction
- Celery task logging
- FastAPI middleware
"""

from __future__ import annotations

import json
import logging
import os
import sys
import time
import traceback
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any
from uuid import uuid4

if TYPE_CHECKING:
    pass

# ─────────────────────────────────────────────────────────────────────────────
# Context Variables (Thread/Async-Safe)
# ─────────────────────────────────────────────────────────────────────────────

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")
workspace_id_var: ContextVar[int | None] = ContextVar("workspace_id", default=None)
task_id_var: ContextVar[str] = ContextVar("task_id", default="")
task_name_var: ContextVar[str] = ContextVar("task_name", default="")
queue_name_var: ContextVar[str] = ContextVar("queue_name", default="")
worker_id_var: ContextVar[str] = ContextVar("worker_id", default="")
request_id_var: ContextVar[str] = ContextVar("request_id", default="")


def get_trace_id() -> str:
    """Get current trace ID or empty string."""
    return trace_id_var.get()


def set_trace_id(trace_id: str | None = None) -> str:
    """Set trace ID, generating one if not provided."""
    if trace_id is None:
        trace_id = str(uuid4())[:12]
    trace_id_var.set(trace_id)
    return trace_id


def get_workspace_id() -> int | None:
    """Get current workspace ID."""
    return workspace_id_var.get()


def set_workspace_id(workspace_id: int | None) -> None:
    """Set current workspace ID."""
    workspace_id_var.set(workspace_id)


def get_task_id() -> str:
    """Get current task ID."""
    return task_id_var.get()


def set_task_id(task_id: str) -> None:
    """Set current task ID."""
    task_id_var.set(task_id)


def get_task_name() -> str:
    """Get current task name."""
    return task_name_var.get()


def set_task_name(task_name: str) -> None:
    """Set current task name."""
    task_name_var.set(task_name)


def get_queue_name() -> str:
    """Get current queue name."""
    return queue_name_var.get()


def set_queue_name(queue_name: str) -> None:
    """Set current queue name."""
    queue_name_var.set(queue_name)


def get_worker_id() -> str:
    """Get current worker ID."""
    return worker_id_var.get()


def set_worker_id(worker_id: str) -> None:
    """Set current worker ID."""
    worker_id_var.set(worker_id)


def get_request_id() -> str:
    """Get current request ID."""
    return request_id_var.get()


def set_request_id(request_id: str) -> None:
    """Set current request ID."""
    request_id_var.set(request_id)


@contextmanager
def log_context(
    trace_id: str | None = None,
    workspace_id: int | None = None,
    task_id: str | None = None,
    task_name: str | None = None,
    queue_name: str | None = None,
    worker_id: str | None = None,
    request_id: str | None = None,
):
    """
    Context manager to set logging context temporarily.

    Usage:
        with log_context(workspace_id=123, task_name="campaign_send"):
            logger.info("Processing campaign")
    """
    tokens = []
    if trace_id is not None:
        tokens.append(trace_id_var.set(trace_id))
    if workspace_id is not None:
        tokens.append(workspace_id_var.set(workspace_id))
    if task_id is not None:
        tokens.append(task_id_var.set(task_id))
    if task_name is not None:
        tokens.append(task_name_var.set(task_name))
    if queue_name is not None:
        tokens.append(queue_name_var.set(queue_name))
    if worker_id is not None:
        tokens.append(worker_id_var.set(worker_id))
    if request_id is not None:
        tokens.append(request_id_var.set(request_id))

    try:
        yield
    finally:
        for token in tokens:
            trace_id_var.reset(token)


# ─────────────────────────────────────────────────────────────────────────────
# Log Levels
# ─────────────────────────────────────────────────────────────────────────────

class LogLevel(str, Enum):
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


# ─────────────────────────────────────────────────────────────────────────────
# PII Redaction
# ─────────────────────────────────────────────────────────────────────────────

class PIIRedactor:
    """Safe logging with automatic PII redaction."""

    # Patterns for sensitive data
    REDACT_PATTERNS = [
        # Phone numbers (various formats)
        (r'\b\d{10,15}\b', '[PHONE]'),
        (r'\+\d{1,3}[-.\s]?\(?\d{1,4}\)?[-.\s]?\d{1,4}[-.\s]?\d{1,9}', '[PHONE]'),
        # Email addresses
        (r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b', '[EMAIL]'),
        # Tokens/keys
        (r'(?i)(api[_-]?key|token|secret|password|auth)[=:\s]+["\']?[\w\-]{8,}["\']?',
         '[REDACTED_KEY]'),
        # Authorization headers
        (r'Bearer\s+[\w\-\.]+', 'Bearer [REDACTED_TOKEN]'),
        # Credit card numbers
        (r'\b\d{4}[-\s]?\d{4}[-\s]?\d{4}[-\s]?\d{4}\b', '[CARD]'),
    ]

    _compiled_patterns: list[tuple[Any, str]] | None = None

    @classmethod
    def _get_patterns(cls) -> list[tuple[Any, str]]:
        if cls._compiled_patterns is None:
            cls._compiled_patterns = [
                (pattern, replacement) for pattern, replacement in cls.REDACT_PATTERNS
            ]
        return cls._compiled_patterns

    @classmethod
    def redact(cls, value: str, redact_phone: bool = False) -> str:
        """
        Redact sensitive information from a string.

        Args:
            value: String to redact
            redact_phone: Whether to redact phone numbers
        """
        if not isinstance(value, str):
            return value

        result = value
        for pattern, replacement in cls._get_patterns():
            if 'PHONE' in replacement and not redact_phone:
                continue
            result = pattern.sub(replacement, result)
        return result

    @classmethod
    def redact_dict(
        cls,
        data: dict,
        redact_phone: bool = False,
        keys_to_redact: list[str] | None = None,
    ) -> dict:
        """
        Recursively redact sensitive fields from a dictionary.

        Args:
            data: Dictionary to redact
            redact_phone: Whether to redact phone numbers
            keys_to_redact: Specific keys to always redact
        """
        if data is None:
            return None

        keys_to_redact = keys_to_redact or [
            "password", "secret", "token", "api_key", "authorization",
            "access_token", "refresh_token", "x-api-key",
        ]

        result = {}
        for key, value in data.items():
            if key.lower() in [k.lower() for k in keys_to_redact]:
                result[key] = "[REDACTED]"
            elif isinstance(value, str):
                result[key] = cls.redact(value, redact_phone)
            elif isinstance(value, dict):
                result[key] = cls.redact_dict(value, redact_phone, keys_to_redact)
            elif isinstance(value, list):
                result[key] = [
                    cls.redact_dict(v, redact_phone, keys_to_redact)
                    if isinstance(v, dict) else cls.redact(v, redact_phone)
                    if isinstance(v, str) else v
                    for v in value
                ]
            else:
                result[key] = value

        return result


# ─────────────────────────────────────────────────────────────────────────────
# Log Schema
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class LogSchema:
    """
    Standardized log schema for ChatPulse.

    Schema:
    {
        timestamp: ISO8601 datetime,
        level: Log level (DEBUG/INFO/WARNING/ERROR/CRITICAL),
        service: Service name (e.g., "chatpulse-api"),
        event: Event name (e.g., "campaign.send.started"),
        trace_id: Correlation ID,
        workspace_id: Workspace context (optional),
        task_name: Celery task name (optional),
        task_id: Celery task ID (optional),
        queue_name: Queue name (optional),
        worker_id: Worker identifier (optional),
        duration_ms: Operation duration (optional),
        status: Status (started/success/failed/completed),
        message: Human-readable message,
        metadata: Additional context (optional)
    }
    """

    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    level: str = "INFO"
    service: str = "chatpulse"
    event: str = ""
    trace_id: str = ""
    workspace_id: int | None = None
    task_name: str = ""
    task_id: str = ""
    queue_name: str = ""
    worker_id: str = ""
    duration_ms: float | None = None
    status: str = ""
    message: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary, excluding empty optional fields."""
        result = {
            "timestamp": self.timestamp,
            "level": self.level,
            "service": self.service,
            "event": self.event,
            "message": self.message,
        }

        # Add optional fields only if they have values
        if self.trace_id:
            result["trace_id"] = self.trace_id
        if self.workspace_id is not None:
            result["workspace_id"] = self.workspace_id
        if self.task_name:
            result["task_name"] = self.task_name
        if self.task_id:
            result["task_id"] = self.task_id
        if self.queue_name:
            result["queue_name"] = self.queue_name
        if self.worker_id:
            result["worker_id"] = self.worker_id
        if self.duration_ms is not None:
            result["duration_ms"] = self.duration_ms
        if self.status:
            result["status"] = self.status
        if self.metadata:
            result["metadata"] = PIIRedactor.redact_dict(self.metadata)

        return result

    def to_json(self) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict())


# ─────────────────────────────────────────────────────────────────────────────
# JSON Formatter
# ─────────────────────────────────────────────────────────────────────────────

class StructuredJsonFormatter(logging.Formatter):
    """Format log records as structured JSON with standardized schema."""

    def __init__(
        self,
        service: str = "chatpulse",
        redact_phone: bool = False,
        **kwargs,
    ):
        super().__init__(**kwargs)
        self.service = service
        self.redact_phone = redact_phone

    def format(self, record: logging.LogRecord) -> str:
        """Format log record as JSON."""
        # Extract custom fields from record
        extra_fields = getattr(record, "_log_schema", {})

        # Build schema
        schema = LogSchema(
            timestamp=datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            level=record.levelname,
            service=self.service,
            event=getattr(record, "event", ""),
            trace_id=getattr(record, "trace_id", "") or get_trace_id(),
            workspace_id=getattr(record, "workspace_id", None) or get_workspace_id(),
            task_name=getattr(record, "task_name", "") or get_task_name(),
            task_id=getattr(record, "task_id", "") or get_task_id(),
            queue_name=getattr(record, "queue_name", "") or get_queue_name(),
            worker_id=getattr(record, "worker_id", "") or get_worker_id(),
            duration_ms=getattr(record, "duration_ms", None),
            status=getattr(record, "status", ""),
            message=record.getMessage(),
            metadata={**extra_fields, **getattr(record, "metadata", {})},
        )

        # Redact PII from metadata
        return schema.to_json()


# ─────────────────────────────────────────────────────────────────────────────
# Logger Wrapper
# ─────────────────────────────────────────────────────────────────────────────

class ChatPulseLogger:
    """
    Logger wrapper with structured logging and context enrichment.

    Usage:
        logger = get_logger(__name__)
        logger.info("campaign.send.started", "Starting campaign send",
                    workspace_id=123, campaign_id=456)

        logger.audit("campaign.created", "Campaign created by user",
                     workspace_id=123, user_id=456)
    """

    def __init__(self, name: str):
        self._logger = logging.getLogger(name)

    def _log(
        self,
        level: int,
        event: str,
        message: str,
        status: str = "",
        duration_ms: float | None = None,
        **kwargs,
    ):
        """Internal log method with context enrichment."""
        extra = {
            "_log_schema": kwargs.pop("_schema", {}),
            "event": event,
            "status": status,
            "duration_ms": duration_ms,
            "trace_id": get_trace_id(),
            "workspace_id": get_workspace_id(),
            "task_name": get_task_name(),
            "task_id": get_task_id(),
            "queue_name": get_queue_name(),
            "worker_id": get_worker_id(),
            **kwargs,
        }
        self._logger.log(level, message, extra=extra)

    def debug(self, event: str, message: str = "", **kwargs):
        """Log debug level."""
        self._log(logging.DEBUG, event, message or event, **kwargs)

    def info(self, event: str, message: str = "", **kwargs):
        """Log info level."""
        self._log(logging.INFO, event, message or event, **kwargs)

    def warning(self, event: str, message: str = "", **kwargs):
        """Log warning level."""
        self._log(logging.WARNING, event, message or event, **kwargs)

    def error(self, event: str, message: str = "", **kwargs):
        """Log error level."""
        self._log(logging.ERROR, event, message or event, status="failed", **kwargs)

    def critical(self, event: str, message: str = "", **kwargs):
        """Log critical level."""
        self._log(logging.CRITICAL, event, message or event, status="failed", **kwargs)

    def audit(self, event: str, message: str = "", **kwargs):
        """Log audit event (INFO level with audit metadata)."""
        self._log(
            logging.INFO,
            f"audit.{event}",
            message or event,
            status="audit",
            _schema={"audit": True},
            **kwargs,
        )

    def audit_warning(self, event: str, message: str = "", **kwargs):
        """Log audit warning event."""
        self._log(
            logging.WARNING,
            f"audit.{event}",
            message or event,
            status="audit_warning",
            _schema={"audit": True},
            **kwargs,
        )

    def exception(
        self,
        event: str,
        message: str = "",
        exc_info: bool | None = None,
        **kwargs,
    ):
        """Log exception with traceback."""
        if exc_info is None:
            exc_info = True
        self._log(logging.ERROR, event, message or event, status="failed", **kwargs)

    @contextmanager
    def timed(self, event: str, **kwargs):
        """
        Context manager to measure and log operation duration.

        Usage:
            with logger.timed("campaign.process"):
                process_campaign()
        """
        start = time.perf_counter()
        try:
            yield
        except Exception:
            duration_ms = (time.perf_counter() - start) * 1000
            self.error(event, f"{event} failed", duration_ms=duration_ms, **kwargs)
            raise
        else:
            duration_ms = (time.perf_counter() - start) * 1000
            self.info(event, f"{event} completed", duration_ms=duration_ms, **kwargs)


# ─────────────────────────────────────────────────────────────────────────────
# Logger Factory
# ─────────────────────────────────────────────────────────────────────────────

_loggers: dict[str, ChatPulseLogger] = {}


def get_logger(name: str) -> ChatPulseLogger:
    """
    Get or create a ChatPulse logger.

    Usage:
        logger = get_logger(__name__)
    """
    if name not in _loggers:
        _loggers[name] = ChatPulseLogger(name)
    return _loggers[name]


# ─────────────────────────────────────────────────────────────────────────────
# Logging Setup
# ─────────────────────────────────────────────────────────────────────────────

def setup_logging(
    level: str = "INFO",
    service: str = "chatpulse",
    redact_phone: bool = False,
    json_format: bool = True,
) -> None:
    """
    Configure logging for the application.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        service: Service name for log schema
        redact_phone: Whether to redact phone numbers in logs
        json_format: Use JSON formatting (default True for production)
    """
    # Get root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Create console handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(getattr(logging, level.upper(), logging.INFO))

    if json_format:
        formatter = StructuredJsonFormatter(
            service=service,
            redact_phone=redact_phone,
        )
    else:
        # Human-readable format for development
        fmt = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
        formatter = logging.Formatter(fmt, datefmt="%Y-%m-%d %H:%M:%S")

    handler.setFormatter(formatter)
    root_logger.addHandler(handler)

    # Reduce noise from third-party libraries
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("celery.app.trace").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
    logging.getLogger("alembic").setLevel(logging.WARNING)


# ─────────────────────────────────────────────────────────────────────────────
# Celery Integration
# ─────────────────────────────────────────────────────────────────────────────

class CeleryTaskFormatter(StructuredJsonFormatter):
    """Extended formatter for Celery tasks with automatic context."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Try to get worker ID from environment or hostname
        self._worker_id = os.environ.get("CELERY_WORKER_ID", os.environ.get("HOSTNAME", "unknown"))

    def format(self, record: logging.LogRecord) -> str:
        """Add Celery-specific context to log record."""
        # Add worker context
        record.worker_id = self._worker_id

        # If this is a task log, extract task context
        if hasattr(record, "task_name"):
            record.task_name = record.task_name
        elif hasattr(record, "task_id"):
            # Try to extract from task_id
            pass

        return super().format(record)


def setup_celery_logging(service: str = "chatpulse-worker"):
    """Configure logging for Celery workers."""
    setup_logging(
        level=os.environ.get("LOG_LEVEL", "INFO"),
        service=service,
        json_format=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Exported Symbols
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    # Context management
    "get_trace_id",
    "set_trace_id",
    "get_workspace_id",
    "set_workspace_id",
    "get_task_id",
    "set_task_id",
    "get_task_name",
    "set_task_name",
    "get_queue_name",
    "set_queue_name",
    "get_worker_id",
    "set_worker_id",
    "get_request_id",
    "set_request_id",
    "log_context",
    # Logger
    "get_logger",
    "ChatPulseLogger",
    # Setup
    "setup_logging",
    "setup_celery_logging",
    # Schema and utilities
    "LogSchema",
    "PIIRedactor",
    "LogLevel",
]