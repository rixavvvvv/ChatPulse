# Observability Strategy

> Logging standards, correlation IDs, metrics, traces, alerts, and dashboards. Last updated: 2026-05-12.

---

## Overview

Observability enables understanding system behavior through external outputs. This document defines the strategy for logs, metrics, traces, and alerting.

---

## Logging Standards

### Log Levels

| Level | Usage | Example |
|-------|-------|---------|
| `DEBUG` | Detailed debugging info | Variable values, loop iterations |
| `INFO` | Normal operation events | Task started, message sent |
| `WARNING` | Potential issues | Rate limit approaching, retry |
| `ERROR` | Failures that need attention | API error, validation failed |
| `CRITICAL` | System failures | Database unavailable, worker crash |

### Log Format

```python
# Standard log format
{
    "timestamp": "2026-05-12T10:00:00.000Z",
    "level": "INFO",
    "logger": "app.services.campaign_service",
    "message": "Campaign queued for execution",
    "trace_id": "abc123",
    "workspace_id": 1,
    "campaign_id": 42,
    "task_id": "celery-task-id-xxx"
}
```

### Structured Logging

Use structured JSON logging for machine parsing:

```python
import logging
import json

class StructuredFormatter(logging.Formatter):
    def format(self, record):
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        # Add trace_id if present
        if hasattr(record, 'trace_id'):
            log_data['trace_id'] = record.trace_id
        if hasattr(record, 'workspace_id'):
            log_data['workspace_id'] = record.workspace_id
        return json.dumps(log_data)
```

### What to Log

**Log (INFO level)**:
- Task started/completed
- Campaign queued/started/completed
- Message sent/delivered
- Contact imported (summary)
- Segment materialized
- Webhook received

**Log (WARNING level)**:
- Rate limit approaching threshold
- Retry attempt
- Quota at 80%
- Slow query (>1s)

**Log (ERROR level)**:
- API failures with error details
- Validation failures
- Database connection issues
- Task failures

**Never log**:
- Passwords or tokens
- Full webhook payloads (log hash or count instead)
- PII without masking

### Python Logging Setup

```python
# app/logging.py
import logging
import sys

def setup_logging(level: str = "INFO"):
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredFormatter())
    
    root_logger = logging.getLogger()
    root_logger.setLevel(level)
    root_logger.addHandler(handler)
    
    # Reduce noise from third-party libraries
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("celery").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
```

---

## Correlation IDs

### Trace ID Flow

```
HTTP Request ──► Generate trace_id ──► Store in context
       │                                      │
       ▼                                      ▼
  API Response                           Task kwargs
  (header X-Trace-ID)                    (passed to workers)
       │                                      │
       ▼                                      ▼
  Log output                           Log output
  (with trace_id)                      (with trace_id)
```

### Implementation

```python
# app/tracing.py
from contextvars import ContextVar
import uuid

trace_id_var: ContextVar[str] = ContextVar("trace_id", default="")

def get_trace_id() -> str:
    return trace_id_var.get()

def set_trace_id(trace_id: str | None = None) -> str:
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:12]
    trace_id_var.set(trace_id)
    return trace_id

# Middleware to extract/create trace_id
from starlette.middleware.base import BaseHTTPMiddleware

class TracingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        trace_id = request.headers.get("X-Trace-ID") or str(uuid.uuid4())[:12]
        set_trace_id(trace_id)
        
        response = await call_next(request)
        response.headers["X-Trace-ID"] = trace_id
        return response
```

### Celery Task Propagation

```python
@celery_app.task(bind=True)
def campaign_send(self, workspace_id, campaign_id, trace_id=None):
    if trace_id is None:
        trace_id = str(uuid.uuid4())[:12]
    set_trace_id(trace_id)
    
    logger = logging.getLogger(__name__)
    logger.info(
        "Campaign send task started",
        extra={"trace_id": trace_id, "workspace_id": workspace_id}
    )
    # ... task logic
```

---

## Metrics Naming

### Metric Naming Convention

```
{domain}.{component}.{action}.{status}

Examples:
- campaign.send.started
- campaign.send.completed
- campaign.send.failed
- message.dispatch.sent
- message.dispatch.delivered
- webhook.received
- webhook.processed
- queue.depth
```

### Key Metrics

#### Campaign Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `campaign.send.duration` | Histogram | workspace_id | Time to send all messages |
| `campaign.send.count` | Counter | workspace_id, status | Campaign send attempts |
| `campaign.recipients.total` | Gauge | campaign_id | Total recipients |
| `campaign.recipients.sent` | Gauge | campaign_id | Sent count |
| `campaign.recipients.failed` | Gauge | campaign_id | Failed count |

#### Message Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `message.sent.total` | Counter | workspace_id | Total messages sent |
| `message.delivered.total` | Counter | workspace_id | Total delivered |
| `message.failed.total` | Counter | workspace_id, error_type | Total failures |
| `message.send.duration` | Histogram | workspace_id | Time per send |

#### Queue Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `queue.depth` | Gauge | queue_name | Tasks waiting |
| `queue.latency` | Histogram | task_name | Time in queue |
| `queue.processing.duration` | Histogram | task_name | Task execution time |
| `queue.retries.total` | Counter | task_name | Retry count |

#### Webhook Metrics

| Metric | Type | Labels | Description |
|--------|------|--------|-------------|
| `webhook.received.total` | Counter | source, event_type | Webhooks received |
| `webhook.processed.total` | Counter | source, status | Webhooks processed |
| `webhook.failed.total` | Counter | source, error_type | Webhooks failed |
| `webhook.processing.duration` | Histogram | source | Processing time |

### Prometheus Export

```python
# app/metrics.py
from prometheus_client import Counter, Histogram, Gauge

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

queue_depth = Gauge(
    'queue_depth',
    'Number of tasks in queue',
    ['queue_name']
)
```

---

## Tracing (Distributed)

### OpenTelemetry Integration (Planned)

```python
# app/tracing/otel.py
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.jaeger.thrift import JaegerExporter

provider = TracerProvider()
processor = BatchSpanProcessor(JaegerExporter(endpoint="http://jaeger:14268/api/traces"))
provider.add_span_processor(processor)
trace.set_tracer_provider(provider)

tracer = trace.get_tracer(__name__)

@celery_app.task
def campaign_send(workspace_id, campaign_id):
    with tracer.start_as_current_span("campaign.send") as span:
        span.set_attribute("workspace_id", workspace_id)
        span.set_attribute("campaign_id", campaign_id)
        # ... task logic
```

### Span Hierarchy

```
campaign.send (root span)
├── idempotency.check
├── rate_limit.check
├── billing.check
├── template.build_params
│   └── meta_api.send (external span)
├── tracking.register
└── event.record
```

---

## Alerting

### Alert Definitions

| Alert | Condition | Severity | Action |
|-------|-----------|----------|--------|
| High Failure Rate | `failed/sent > 10%` in 1h | WARNING | Slack |
| Critical Failure Rate | `failed/sent > 25%` in 15m | CRITICAL | Slack + Pager |
| High Queue Depth | `bulk-messages > 100` for 5m | WARNING | Slack |
| Worker Down | No heartbeat in 5m | CRITICAL | Pager |
| High Memory | Worker memory > 80% | WARNING | Slack |
| Database Connection Pool Exhausted | `connections > 80%` for 2m | CRITICAL | Pager |
| Quota Warning | `usage/limit > 80%` | WARNING | Email |
| Webhook Failure Spike | `failures > 50` in 5m | WARNING | Slack |

### Alert Routing

```yaml
# alerts.yaml
alerts:
  - name: campaign_high_failure_rate
    condition: rate(failed/sent) > 0.1
    window: 1h
    severity: warning
    channels:
      - slack: "#alerts"
    
  - name: worker_down
    condition: missing(heartbeat) > 5m
    severity: critical
    channels:
      - pagerduty: "worker-oncall"
```

### Alert Examples

**Campaign Alert**:
```json
{
  "alert": "Campaign Failure Rate",
  "workspace_id": 1,
  "campaign_id": 42,
  "failure_rate": 0.15,
  "threshold": 0.10,
  "duration": "1h",
  "action": "Review failed messages at /admin/campaigns/42"
}
```

**Queue Alert**:
```json
{
  "alert": "Queue Depth High",
  "queue": "bulk-messages",
  "depth": 150,
  "threshold": 100,
  "duration": "5m",
  "action": "Scale up campaign workers"
}
```

---

## Dashboards

### Campaign Overview Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ Campaign Performance                          Last 7 days   │
├─────────────────────────────────────────────────────────────┤
│ Total Sent │ Delivered │ Read │ Failed │ Delivery% │ Read%  │
│   12,450  │   11,800  │ 8,200│  650   │   94.7%   │ 69.5%  │
├─────────────────────────────────────────────────────────────┤
│ [Campaign Timeline - Line Chart]                           │
│ Sent ──── Delivered ──── Read ──── Failed                  │
├─────────────────────────────────────────────────────────────┤
│ Active Campaigns: 3    Queued: 1    Failed: 0              │
│ Quota Used: 12,450 / 50,000 (24.9%)                         │
└─────────────────────────────────────────────────────────────┘
```

### Worker Health Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ Worker Health                                  Live         │
├─────────────────────────────────────────────────────────────┤
│ Queue          │ Depth │ Avg Latency │ Workers │ Status    │
│ bulk-messages  │  12   │   45ms     │   4/4   │ OK        │
│ webhooks       │  234  │   12ms     │  20/20  │ OK        │
│ default        │   3   │   2.1s     │   2/2   │ OK        │
├─────────────────────────────────────────────────────────────┤
│ [Queue Depth Over Time - Stacked Area Chart]               │
│ bulk-messages ████                                           │
│ webhooks      ████████████████████████████                 │
└─────────────────────────────────────────────────────────────┘
```

### Webhook Health Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ Webhook Health                              Last 24h       │
├─────────────────────────────────────────────────────────────┤
│ Source     │ Received │ Processed │ Failed │ Latency p99     │
│ Meta       │  45,230  │   45,200  │   30   │   45ms        │
│ Shopify    │   1,234  │    1,234  │    0   │   23ms       │
├─────────────────────────────────────────────────────────────┤
│ [Processing Timeline - Bar Chart]                          │
│ ████████████████████████████                              │
└─────────────────────────────────────────────────────────────┘
```

### Workspace Usage Dashboard

```
┌─────────────────────────────────────────────────────────────┐
│ Workspace Usage                         Billing Cycle: May │
├─────────────────────────────────────────────────────────────┤
│ Workspace        │ Used      │ Limit    │ Usage% │ Status   │
│ Acme Corp        │  45,230   │  50,000  │  90.5% │ ⚠️      │
│ Demo Workspace   │   1,234   │  10,000  │  12.3% │ OK      │
├─────────────────────────────────────────────────────────────┤
│ [Usage Trend - Area Chart]                                 │
│ ████████████████████████████████████████████               │
└─────────────────────────────────────────────────────────────┘
```

---

## Observability Stack (Future)

### Recommended Tools

| Component | Tool | Purpose |
|-----------|------|---------|
| Metrics | Prometheus + Grafana | Time-series metrics, dashboards |
| Logs | Loki + Grafana | Log aggregation, search |
| Traces | Jaeger | Distributed tracing |
| Alerts | Alertmanager + PagerDuty | Alert routing |
| APM | Sentry | Error tracking, performance |

### Docker Compose (Future)

```yaml
version: '3.8'
services:
  prometheus:
    image: prom/prometheus
    ports: ["9090:9090"]
    
  grafana:
    image: grafana/grafana
    ports: ["3001:3000"]
    
  loki:
    image: grafana/loki
    ports: ["3100:3100"]
    
  jaeger:
    image: jaegertracing/all-in-one
    ports: ["16686:16686"]
```

---

## SLOs (Service Level Objectives)

### Current SLOs (Planned)

| SLO | Target | Current |
|-----|--------|---------|
| Message delivery rate | > 95% | N/A |
| Campaign send latency (p99) | < 5s per message | N/A |
| Webhook processing latency (p99) | < 100ms | N/A |
| API response latency (p99) | < 500ms | N/A |
| System uptime | > 99.9% | N/A |

### Error Budget

```
Monthly error budget = (1 - SLO_target) * total_requests

Example:
- Target SLO: 99.9%
- Expected requests/month: 1,000,000
- Error budget: 1,000,000 * 0.001 = 1,000 errors
```

---

## Implementation Checklist

### Phase 1: Basic Observability (Now)

- [x] Structured logging with trace_id
- [x] Error logging with context
- [x] Queue depth monitoring via `/admin/queues/inspect`
- [x] Dead letter tracking

### Phase 2: Metrics (Next Sprint)

- [ ] Prometheus client integration
- [ ] Campaign metrics export
- [ ] Message metrics export
- [ ] Queue metrics export
- [ ] Grafana dashboard setup

### Phase 3: Tracing (Future)

- [ ] OpenTelemetry integration
- [ ] Celery task tracing
- [ ] Jaeger setup
- [ ] Trace correlation UI

### Phase 4: Alerting (Future)

- [ ] Alertmanager setup
- [ ] Alert routing rules
- [ ] PagerDuty integration
- [ ] On-call rotation

### Phase 5: Advanced (Future)

- [ ] APM (Sentry) integration
- [ ] Log aggregation (Loki)
- [ ] Error budget tracking
- [ ] SLO dashboard
