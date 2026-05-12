# Metrics Collection Architecture

Centralized metrics infrastructure for ChatPulse with Redis-backed aggregation and OpenTelemetry/Prometheus readiness.

## Overview

The metrics system provides:
- Centralized metrics registry
- Multiple metric types (counters, histograms, gauges)
- Redis-backed temporary storage with aggregation
- Background aggregation workers
- Retention policies
- OpenTelemetry/Prometheus-ready design

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          METRICS ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Application Code                                    │  │
│  │                                                                       │  │
│  │   Queue Workers    │   Webhook   │   Dispatch   │   Campaigns        │  │
│  │        │              │             │              │                    │  │
│  │        └──────────────┴─────────────┴──────────────┘                  │  │
│  │                              │                                          │  │
│  │                              ▼                                          │  │
│  │                     ┌────────────────┐                                │  │
│  │                     │  Metrics Hooks  │                                │  │
│  │                     │  (hooks.py)     │                                │  │
│  │                     └────────┬───────┘                                │  │
│  └───────────────────────────────│────────────────────────────────────────┘  │
│                                  │                                          │
│                                  ▼                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Metrics Registry                                    │  │
│  │  ┌────────────┐  ┌────────────┐  ┌────────────┐  ┌────────────┐     │  │
│  │  │  Counter   │  │  Histogram │  │   Gauge    │  │   Timer    │     │  │
│  │  └────────────┘  └────────────┘  └────────────┘  └────────────┘     │  │
│  └──────────────────────────────┬───────────────────────────────────────┘  │
│                                 │                                            │
│                    ┌────────────┴────────────┐                             │
│                    │                         │                             │
│                    ▼                         ▼                             │
│         ┌──────────────────┐      ┌──────────────────┐                   │
│         │  Redis Cache     │      │  Local Cache      │                   │
│         │  (metrics:raw)  │      │  (fallback)       │                   │
│         └────────┬─────────┘      └──────────────────┘                    │
│                  │                                                       │
│                  ▼                                                       │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                  Aggregation Workers                                  │  │
│  │  ┌─────────┐    ┌─────────┐    ┌─────────┐    ┌─────────┐           │  │
│  │  │  1m →   │───▶│  5m →   │───▶│  1h →   │───▶│  1d →   │           │  │
│  │  │  raw    │    │  1m     │    │  5m     │    │  1h     │           │  │
│  │  └─────────┘    └─────────┘    └─────────┘    └─────────┘           │  │
│  │                                                                   │  │
│  └───────────────────────────────────────────────────────────────────────┘  │
│                                                                              │
│  ┌────────────────────────────────────────────────────────────────────────┐ │
│  │                  Storage (Future Integrations)                          │ │
│  │                                                                        │ │
│  │   Prometheus    │    OpenTelemetry    │    Grafana / Loki            │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Metric Types

### Counters
- **Purpose**: Track cumulative counts
- **Behavior**: Only increment (can reset on restart)
- **Use Cases**: `campaign.sent`, `message.failed`, `webhook.received`

```python
await increment_counter(MetricName.CAMPAIGN_SENT, labels={"workspace_id": "123"})
```

### Histograms
- **Purpose**: Track distributions of values
- **Behavior**: Record any value, calculate percentiles
- **Use Cases**: `campaign.duration`, `webhook.latency`, `api.request.duration`

```python
await record_histogram(
    MetricName.CAMPAIGN_DURATION,
    value=1500.5,  # milliseconds
    labels={"campaign_id": "456"}
)
```

### Gauges
- **Purpose**: Track current values
- **Behavior**: Can go up or down
- **Use Cases**: `queue.depth`, `worker.active`, `recipients.sent`

```python
await record_gauge(MetricName.QUEUE_DEPTH, value=42, labels={"queue_name": "bulk-messages"})
```

### Timers
- **Purpose**: Convenience for duration tracking
- **Behavior**: Context manager or decorator

```python
with timing_context("campaign.process", {"workspace_id": "123"}):
    process_campaign()
```

## Metrics Lifecycle

### 1. Collection

```
Application Code
      │
      │  metrics.increment_counter("campaign.sent", ...)
      │  metrics.record_histogram("campaign.duration", 1500.5, ...)
      │  metrics.record_gauge("queue.depth", 42, ...)
      │
      ▼
Metrics Registry
      │
      │  _record_metric(metric)
      │
      ▼
Redis Raw Storage
      │
      │  ZADD metrics:raw:campaign.sent {labels} timestamp
      │  HSET metrics:values:campaign.sent {labels} value
      │  ZADD metrics:keys {name:labels} timestamp
      │
      ▼
Local Cache (fallback if Redis unavailable)
```

### 2. Aggregation

```
Raw Metrics (1m resolution)
      │
      │  Aggregate Loop (every 1 minute)
      │
      ▼
1-Minute Aggregates
      │
      │  Aggregate Loop (every 5 minutes)
      │
      ▼
5-Minute Aggregates
      │
      │  Aggregate Loop (every 1 hour)
      │
      ▼
1-Hour Aggregates
      │
      │  Daily Rollup (every 1 day)
      │
      ▼
1-Day Aggregates
```

### 3. Aggregation Strategies

| Metric Type | Strategy | Description |
|-------------|----------|-------------|
| Counter | Sum | Total count across interval |
| Histogram | Average + Percentiles | Mean value, P50/P95/P99 |
| Gauge | Last Value | Current value at interval end |

### 4. Retention Policy

| Bucket | Resolution | Retention | Storage |
|--------|------------|-----------|---------|
| Raw | 1 minute | 1 hour | Redis |
| 1m | 1 minute | 7 days | Redis |
| 5m | 5 minutes | 30 days | Redis |
| 1h | 1 hour | 90 days | Redis |
| 1d | 1 day | 365 days | Redis |

## Eventual Consistency

The metrics system uses eventual consistency for aggregation:

### Write Path
1. Metrics written to Redis immediately
2. Client receives acknowledgment
3. Aggregation runs in background

### Read Path
1. Current values from Redis
2. Aggregated values from aggregation storage
3. Stale reads possible but bounded (< 1 minute)

### Consistency Guarantees
- **Write**: At-least-once (metrics may be lost on crash)
- **Read**: Eventual consistency (< 60s lag)
- **Accuracy**: Counters may be slightly underestimated

### Fallback Behavior
If Redis is unavailable:
1. Metrics stored in local memory cache
2. Client operation continues without blocking
3. Cache flushed when Redis reconnects

## Redis Data Structure

### Raw Metrics
```
metrics:raw:{metric_name}        → Sorted Set (timestamp → labels_key)
metrics:values:{metric_name}     → Hash (labels_key → value)
metrics:labels:{metric_name}     → Hash (labels_key → label_values)
```

### Aggregated Metrics
```
metrics:agg:1m:{metric_name}     → Hash (labels_key → {sum, count, min, max})
metrics:agg:5m:{metric_name}     → Hash (labels_key → {sum, count, min, max})
metrics:agg:1h:{metric_name}     → Hash (labels_key → {sum, count, min, max})
```

### Key Management
```
metrics:keys                     → Sorted Set (name:labels_key → timestamp)
metrics:aggregated               → Hash (full_key → value)
```

## Metric Names

### Naming Convention
```
{domain}.{component}.{action}.{status}

Examples:
- campaign.send.started
- campaign.send.completed
- campaign.recipients.sent
- webhook.processed.success
- message.dispatch.failed
- rate_limit.allowed
```

### Standard Metrics

| Name | Type | Labels | Description |
|------|------|--------|-------------|
| `queue.depth` | Gauge | queue_name | Tasks waiting in queue |
| `queue.published` | Counter | queue_name | Tasks published |
| `queue.consumed` | Counter | queue_name | Tasks consumed |
| `queue.latency` | Histogram | queue_name, task_name | Time in queue |
| `queue.task.duration` | Histogram | task_name, status | Task execution time |
| `webhook.received` | Counter | source, event_type | Webhooks received |
| `webhook.processed` | Counter | source, status | Webhooks processed |
| `webhook.failed` | Counter | source, error_type | Webhooks failed |
| `webhook.latency` | Histogram | source | Processing time |
| `campaign.created` | Counter | workspace_id | Campaigns created |
| `campaign.sent` | Counter | workspace_id | Messages sent |
| `campaign.failed` | Counter | workspace_id, error_type | Send failures |
| `campaign.duration` | Histogram | workspace_id | Campaign duration |
| `campaign.recipients.total` | Gauge | campaign_id | Total recipients |
| `campaign.recipients.sent` | Gauge | campaign_id | Sent count |
| `campaign.recipients.failed` | Gauge | campaign_id | Failed count |
| `message.sent` | Counter | workspace_id | Messages sent |
| `message.delivered` | Counter | workspace_id | Deliveries confirmed |
| `message.failed` | Counter | workspace_id, error_type | Send failures |
| `message.dispatch.duration` | Histogram | workspace_id | Dispatch time |
| `api.request.duration` | Histogram | method, path, status | API latency |
| `api.request.count` | Counter | method, path, status | API requests |
| `api.error.count` | Counter | method, path, status | API errors |
| `worker.active` | Gauge | worker_id | Active workers |
| `worker.error` | Counter | worker_id, error_type | Worker errors |
| `worker.task.duration` | Histogram | worker_id, task_name | Task duration |
| `recovery.detected` | Counter | workspace_id | Stale campaigns |
| `recovery.completed` | Counter | workspace_id | Recoveries |
| `recovery.failed` | Counter | workspace_id, error_type | Failures |
| `recovery.duration` | Histogram | workspace_id | Recovery time |
| `rate_limit.allowed` | Counter | limit_type | Allowed requests |
| `rate_limit.rejected` | Counter | limit_type | Rejected requests |
| `redis.operations` | Histogram | operation, status | Redis latency |
| `redis.errors` | Counter | operation, error_type | Redis errors |

## Hooks Usage

### Queue Worker Hooks

```python
from app.metrics.hooks import QueueWorkerMetrics

# Task start
await QueueWorkerMetrics.record_task_start(
    task_name="campaign.send",
    task_id="abc123",
    queue_name="bulk-messages",
    worker_id="worker-1",
)

# Task complete
await QueueWorkerMetrics.record_task_complete(
    task_name="campaign.send",
    task_id="abc123",
    duration_ms=1500.5,
    queue_name="bulk-messages",
    success=True,
)

# Task error
await QueueWorkerMetrics.record_task_error(
    task_name="campaign.send",
    task_id="abc123",
    error_type="rate_limit",
    queue_name="bulk-messages",
)
```

### Webhook Hooks

```python
from app.metrics.hooks import WebhookMetrics

# Webhook received
await WebhookMetrics.record_webhook_received(
    source="meta",
    event_type="message_delivery",
    payload_size=1024,
)

# Webhook processed
await WebhookMetrics.record_webhook_processed(
    source="meta",
    event_type="message_delivery",
    duration_ms=45.2,
    success=True,
    workspace_id=123,
)
```

### Campaign Hooks

```python
from app.metrics.hooks import CampaignMetrics

# Campaign created
await CampaignMetrics.record_campaign_created(
    campaign_id=456,
    workspace_id=123,
    recipient_count=1000,
)

# Campaign progress
await CampaignMetrics.record_campaign_progress(
    campaign_id=456,
    workspace_id=123,
    processed=500,
    total=1000,
    success_count=490,
    failed_count=10,
)

# Campaign complete
await CampaignMetrics.record_campaign_complete(
    campaign_id=456,
    workspace_id=123,
    duration_ms=60000.0,
    success_count=980,
    failed_count=20,
)
```

### Recovery Hooks

```python
from app.metrics.hooks import RecoveryMetrics

# Recovery started
await RecoveryMetrics.record_recovery_start(
    campaign_id=456,
    workspace_id=123,
)

# Recovery complete
await RecoveryMetrics.record_recovery_complete(
    campaign_id=456,
    workspace_id=123,
    duration_ms=5000.0,
    success=True,
    recipients_resumed=50,
)
```

### Timing Decorators

```python
from app.metrics.hooks import timed_operation

@timed_operation("campaign.process", {"workspace_id": "123"})
async def process_campaign():
    # ... processing ...
    pass
```

## Prometheus Integration (Future)

The architecture is designed for easy Prometheus integration:

```python
# When ready for Prometheus
from prometheus_client import Counter, Histogram, Gauge, CollectorRegistry

registry = CollectorRegistry()

campaign_sent = Counter(
    'chatpulse_campaign_sent_total',
    'Campaign messages sent',
    ['workspace_id'],
    registry=registry,
)

campaign_duration = Histogram(
    'chatpulse_campaign_duration_seconds',
    'Campaign duration',
    ['workspace_id'],
    buckets=(1, 5, 10, 30, 60, 300, 600),
    registry=registry,
)
```

## OpenTelemetry Integration (Future)

```python
# When ready for OpenTelemetry
from opentelemetry import metrics
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.resources import Resource

# Configure meter provider
resource = Resource.create({"service.name": "chatpulse"})
provider = MeterProvider(resource=resource)
metrics.set_meter_provider(provider)

# Create meter and instruments
meter = metrics.get_meter(__name__)
counter = meter.create_counter("campaign.sent")
histogram = meter.create_histogram("campaign.duration")
```

## Query Examples

### Current Value
```python
from app.metrics.aggregation import MetricsQueryService

query = MetricsQueryService(redis_client)
queue_depth = await query.get_current("queue.depth", {"queue_name": "bulk-messages"})
```

### Histogram Stats
```python
stats = await query.get_histogram_stats("campaign.duration", {"workspace_id": "123"})
# Returns: {"min": 100, "max": 5000, "avg": 1500, "p50": 1400, "p95": 3000, "p99": 4500}
```

### Time Series
```python
from datetime import datetime, timedelta

series = await query.get_time_series(
    "api.request.duration",
    {"method": "GET", "path": "/api/campaigns"},
    bucket="1m",
    start_time=datetime.utcnow() - timedelta(hours=1),
)
```

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Increment counter | < 1ms | Async, non-blocking |
| Record histogram | < 1ms | Async, non-blocking |
| Record gauge | < 1ms | Async, non-blocking |
| Flush to Redis | 10-50ms | Batched, 60s interval |
| Aggregation | 100-500ms | Per bucket, 1-5 minute intervals |
| Query current | < 5ms | Redis GET |
| Query time series | 10-50ms | Redis SCAN |

## Monitoring Recommendations

### Key Dashboards

1. **System Overview**
   - Queue depths across all queues
   - Worker count and status
   - Redis latency and errors

2. **Campaign Performance**
   - Campaign duration percentiles
   - Success/failure rates
   - Recipients processed

3. **API Health**
   - Request latency P50/P95/P99
   - Error rate by endpoint
   - Request volume by method

4. **Recovery Health**
   - Stale campaigns detected
   - Recovery success rate
   - Recovery duration

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| queue.depth | > 50 | > 100 |
| campaign.duration.p99 | > 5min | > 10min |
| api.error.rate | > 1% | > 5% |
| recovery.failures | > 5/hr | > 10/hr |
| redis.latency.p99 | > 50ms | > 100ms |