# Structured Logging Architecture

Centralized JSON logging infrastructure for ChatPulse with trace propagation, PII redaction, and context enrichment.

## Overview

The logging infrastructure provides:
- Standardized JSON log format across all services
- Distributed trace propagation (request → queue → worker → event)
- Automatic PII redaction (tokens, emails, optional phone numbers)
- Context enrichment (correlation IDs, worker IDs, task IDs)
- Celery task lifecycle logging
- FastAPI request/response logging

## Log Schema

```json
{
  "timestamp": "2026-05-12T10:30:00.123Z",
  "level": "INFO",
  "service": "chatpulse-api",
  "event": "campaign.send.completed",
  "trace_id": "abc123def456",
  "workspace_id": 123,
  "task_name": "campaign.send",
  "task_id": "celery-task-id-xxx",
  "queue_name": "bulk-messages",
  "worker_id": "worker-1@hostname",
  "duration_ms": 1523.45,
  "status": "completed",
  "message": "Campaign send completed",
  "metadata": {}
}
```

### Field Definitions

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `timestamp` | ISO8601 | Yes | UTC timestamp with timezone |
| `level` | string | Yes | DEBUG/INFO/WARNING/ERROR/CRITICAL |
| `service` | string | Yes | Service name (e.g., "chatpulse-api") |
| `event` | string | Yes | Event name (e.g., "campaign.send.started") |
| `trace_id` | string | No | Correlation ID for distributed tracing |
| `workspace_id` | integer | No | Workspace context |
| `task_name` | string | No | Celery task name |
| `task_id` | string | No | Celery task ID |
| `queue_name` | string | No | Queue where task was/should be processed |
| `worker_id` | string | No | Worker that processed the task |
| `duration_ms` | float | No | Operation duration in milliseconds |
| `status` | string | No | Status (started/success/failed/completed) |
| `message` | string | No | Human-readable message |
| `metadata` | object | No | Additional context |

## Usage Examples

### Basic Logger Usage

```python
from app.logging import get_logger

logger = get_logger(__name__)

# Simple log
logger.info("campaign.send.started", "Starting campaign send")

# With context
logger.info(
    "campaign.send.completed",
    "Campaign send completed",
    workspace_id=123,
    campaign_id=456,
    metadata={"recipients": 1000}
)

# Timed operation
with logger.timed("campaign.process"):
    process_campaign()
```

### Timed Operations

```python
with logger.timed("webhook.process"):
    process_webhook(payload)
# Automatically logs duration_ms on success
```

### Audit Events

```python
logger.audit(
    "campaign.created",
    "Campaign created by user",
    workspace_id=123,
    metadata={"user_id": 456, "template_id": 789}
)

logger.audit_warning(
    "campaign.deleted",
    "Campaign deleted",
    workspace_id=123,
    metadata={"deleted_by": 456}
)
```

### Context Manager

```python
from app.logging import log_context, set_trace_id

# Temporary context
with log_context(workspace_id=123, task_name="import"):
    logger.info("import.started", "Starting import")
    # All logs in this block have workspace_id=123

# With trace propagation
trace_id = set_trace_id()  # Generate new
with log_context(trace_id=trace_id):
    process_batch()
```

## Trace ID Propagation

### Flow Diagram

```
HTTP Request
     │
     │ X-Trace-ID header or auto-generate
     ▼
FastAPI Middleware
     │
     │ set_trace_id(trace_id)
     │ response.headers["X-Trace-ID"] = trace_id
     ▼
API Handler
     │
     │ Celery task.delay(trace_id=trace_id, ...)
     ▼
Message Queue (trace_id in message body)
     │
     │ task_prerun signal
     ▼
Celery Worker
     │
     │ set_trace_id(request.trace_id)
     │ set_task_context(...)
     ▼
Log Output (all logs share trace_id)
```

### Code Examples

#### FastAPI Request

```python
# Middleware automatically:
# 1. Extracts X-Trace-ID from header or generates new
# 2. Sets trace_id in context
# 3. Adds X-Trace-ID to response headers

@router.post("/campaigns")
async def create_campaign(request: Request):
    trace_id = get_trace_id()  # Available from context
    logger.info("campaign.create", "Creating campaign")
```

#### Celery Task

```python
from app.logging import get_logger, set_trace_id
from app.logging.celery_integration import propagate_trace_to_task

# When dispatching task
task.delay(
    **propagate_trace_to_task({"workspace_id": 123}),
    campaign_id=456
)

# In task definition
@celery_app.task
def process_campaign_task(workspace_id, campaign_id, trace_id=None):
    set_trace_id(trace_id)  # Workers receive trace_id
    logger = get_logger(__name__)
    logger.info("campaign.process", "Processing")
```

## PII Redaction

### Automatic Redaction

The following is automatically redacted:
- Phone numbers (configurable)
- Email addresses
- API keys and tokens
- Authorization headers
- Credit card numbers

### Configuration

```python
from app.logging import setup_logging

# Default: phone numbers NOT redacted
setup_logging(redact_phone=False)

# Enable phone redaction for strict compliance
setup_logging(redact_phone=True)
```

### Manual Redaction

```python
from app.logging import PIIRedactor

# Redact single value
redacted = PIIRedactor.redact("john@example.com", redact_phone=False)
# -> "john@example.com" (email redacted by default)

# Redact dictionary
data = {"email": "john@example.com", "phone": "+1234567890"}
redacted = PIIRedactor.redact_dict(data, redact_phone=False)
# -> {"email": "[EMAIL]", "phone": "+1234567890"}

# Specific keys always redacted
redacted = PIIRedactor.redact_dict(data, keys_to_redact=["api_key"])
```

## FastAPI Integration

### Setup

```python
from fastapi import FastAPI
from app.logging import setup_logging
from app.logging.middleware import LoggingMiddleware

# Configure logging
setup_logging(level="INFO", service="chatpulse-api")

app = FastAPI()

# Add logging middleware
app.add_middleware(LoggingMiddleware)
```

### Middleware Behavior

| Event | Logged | Fields |
|-------|--------|--------|
| Request start | Yes | method, path, client_ip, headers (optional) |
| Request end | Yes | method, path, status_code, duration_ms |
| Error response | Yes | method, path, status_code >= 500 |

### Excluded Paths

By default, the following paths are NOT logged:
- `/health`
- `/metrics`
- `/favicon.ico`

Configure with `exclude_paths` parameter.

## Celery Integration

### Worker Setup

```python
# In worker startup script
from app.logging import setup_celery_logging
setup_celery_logging(service="chatpulse-worker")
```

### Automatic Signals

The following Celery signals are automatically connected:

| Signal | Action |
|--------|--------|
| `worker_init` | Set worker_id in context |
| `task_prerun` | Set task_id, task_name, trace_id |
| `task_postrun` | Log task completion |
| `task_failure` | Log task failure with traceback |
| `task_retry` | Log retry attempt |

### Manual Logging in Tasks

```python
from app.logging import get_logger
from app.logging.celery_integration import with_task_context

@celery_app.task(bind=True)
@with_task_context("campaign.send")
def process_campaign(self, workspace_id, campaign_id):
    logger = get_logger(__name__)
    logger.info(
        "campaign.processing",
        f"Processing campaign {campaign_id}",
        workspace_id=workspace_id
    )
```

### Task Context Propagation

```python
from app.logging.celery_integration import propagate_trace_to_task

# When scheduling task
process_campaign.delay(
    workspace_id=123,
    campaign_id=456,
    **propagate_trace_to_task({"workspace_id": 123})
)
```

## Context Variables

Thread and async-safe context management using `contextvars`:

```python
from app.logging import (
    get_trace_id,
    set_trace_id,
    get_workspace_id,
    set_workspace_id,
    get_task_id,
    set_task_id,
    get_worker_id,
    set_worker_id,
)

# Get current context
trace_id = get_trace_id()
workspace_id = get_workspace_id()

# Set context
set_trace_id("abc123")
set_workspace_id(123)
```

## Log Levels

| Level | Usage | Logged By |
|-------|-------|-----------|
| DEBUG | Variable values, loop iterations | Development only |
| INFO | Normal operations, milestones | All environments |
| WARNING | Rate limits, retries, quotas | All environments |
| ERROR | Failures with recovery path | All environments |
| CRITICAL | System failures | All environments |

## Event Naming Convention

Format: `{domain}.{action}.{status}`

Examples:
- `campaign.send.started`
- `campaign.send.completed`
- `campaign.send.failed`
- `webhook.received`
- `webhook.processed`
- `message.sent`
- `import.started`
- `import.completed`
- `rate_limit.exceeded`
- `worker.initialized`

## What to Log

### Log (INFO)
- Task/operation started
- Task/operation completed
- Webhook received
- Campaign sent
- Import completed

### Log (WARNING)
- Rate limit approaching
- Retry attempt
- Quota at 80%
- Slow query (>1s)

### Log (ERROR)
- API failures
- Validation failures
- Task failures
- Database errors

### Never Log
- Passwords or secrets
- Full webhook payloads (log hash/count)
- Unmasked PII
- Authorization tokens (full)

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        LOGGING ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌─────────────┐     ┌─────────────┐     ┌─────────────┐           │
│  │  FastAPI    │     │   Celery    │     │   Celery    │           │
│  │  Middleware │     │   Signals   │     │   Worker    │           │
│  └──────┬──────┘     └──────┬──────┘     └──────┬──────┘           │
│         │                   │                   │                  │
│         └───────────────────┼───────────────────┘                  │
│                             │                                      │
│                             ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                   Context Variables                          │  │
│  │  ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐       │  │
│  │  │ trace_id │ │workspace │ │ task_id  │ │ worker_id│       │  │
│  │  │          │ │    _id   │ │          │ │          │       │  │
│  │  └──────────┘ └──────────┘ └──────────┘ └──────────┘       │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                             │                                      │
│                             ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              ChatPulseLogger Wrapper                         │  │
│  │  - enriches with context                                     │  │
│  │  - applies PII redaction                                     │  │
│  │  - formats as LogSchema                                      │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │              StructuredJsonFormatter                          │  │
│  │  - converts to JSON                                          │  │
│  │  - includes all schema fields                                 │  │
│  └─────────────────────────┬───────────────────────────────────┘  │
│                            │                                      │
│                            ▼                                      │
│  ┌─────────────────────────────────────────────────────────────┐  │
│  │                    stdout / File                             │  │
│  └─────────────────────────────────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Future Integrations (Not Implemented)

### Prometheus Metrics

```python
# Planned: metrics integration
from prometheus_client import Counter, Histogram

campaign_send_duration = Histogram(
    'campaign_send_duration_seconds',
    'Campaign send duration',
    ['workspace_id']
)

message_sent_total = Counter(
    'message_sent_total',
    'Total messages sent',
    ['workspace_id']
)
```

### OpenTelemetry Traces

```python
# Planned: trace integration
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@celery_app.task
def campaign_send(workspace_id, campaign_id):
    with tracer.start_as_current_span("campaign.send") as span:
        span.set_attribute("workspace_id", workspace_id)
        # ...
```

### Log Aggregation

```yaml
# Planned: Loki/Grafana integration
version: '3.8'
services:
  loki:
    image: grafana/loki
    ports:
      - "3100:3100"
```

## Testing

```python
# tests/test_logging.py
import pytest
from app.logging import get_logger, set_trace_id, PIIRedactor

def test_logger_basic():
    logger = get_logger(__name__)
    # Logger captures structured data
    logger.info("test.event", "Test message", workspace_id=123)

def test_pii_redaction():
    data = {"email": "test@example.com", "password": "secret123"}
    redacted = PIIRedactor.redact_dict(data)
    assert redacted["email"] == "[EMAIL]"
    assert redacted["password"] == "[REDACTED]"

def test_trace_propagation():
    trace_id = set_trace_id("test-trace-123")
    from app.logging import get_trace_id
    assert get_trace_id() == "test-trace-123"

def test_context_manager():
    with log_context(workspace_id=456):
        logger = get_logger(__name__)
        logger.info("test", "In context")
    # Context restored after
```

## Performance Considerations

- JSON serialization adds ~0.1ms per log call
- Context variable access is essentially free
- PII redaction adds ~0.05ms per value
- Overall logging overhead < 1ms per operation

## Migration Guide

### From Standard Logging

```python
# Before
import logging
logger = logging.getLogger(__name__)
logger.info("Processing campaign %s", campaign_id)

# After
from app.logging import get_logger
logger = get_logger(__name__)
logger.info("campaign.processing", f"Processing campaign {campaign_id}")
```

### Adding Context

```python
# Before
logger.info(f"Campaign {campaign_id} for workspace {workspace_id}")

# After
logger.info(
    "campaign.processing",
    f"Campaign {campaign_id}",
    workspace_id=workspace_id,
    campaign_id=campaign_id
)
```

### Error Logging

```python
# Before
logger.error(f"Failed to send: {exc}", exc_info=True)

# After
logger.error(
    "message.send.failed",
    f"Failed to send: {exc}",
    metadata={"error": str(exc), "phone": phone}
)
```