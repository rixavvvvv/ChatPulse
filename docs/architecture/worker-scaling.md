# Worker Scaling

> Scaling philosophy, isolation strategy, and concurrency settings. Last updated: 2026-05-12.

---

## Overview

Workers process async tasks. Different task types have different characteristics and scaling requirements.

---

## Task Characteristics

### CPU-Bound Tasks

| Task | Characteristics |
|------|----------------|
| `campaign.send` | Contact iteration, template building |
| `bulk.send` | Similar to campaign |
| `contacts.import_job` | CSV parsing, batch processing |

**Behavior**: Moderate CPU usage, memory proportional to batch size.

### I/O-Bound Tasks

| Task | Characteristics |
|------|----------------|
| `webhook.dispatch` | HTTP requests, parsing |
| `webhook.process` | Fast processing, minimal CPU |

**Behavior**: High I/O wait, low CPU usage.

### Hybrid Tasks

| Task | Characteristics |
|------|----------------|
| `segments.materialize` | Query building, batch inserts |

**Behavior**: Database-heavy, moderate CPU.

---

## Scaling Principles

### 1. Separate by Queue

Each queue has distinct scaling requirements:

```
┌─────────────────────┐
│  Campaign Worker    │  ← 2-4 workers (CPU-bound)
│  Queue: bulk-messages│
└─────────────────────┘

┌─────────────────────┐
│  Webhook Worker     │  ← 10-20 workers (I/O-bound)
│  Queue: webhooks    │
└─────────────────────┘

┌─────────────────────┐
│  Import Worker      │  ← 2 workers (batch processing)
│  Queue: default     │
└─────────────────────┘
```

### 2. Scale Horizontally

Add more workers as load increases:

```bash
# Scale campaign workers
celery -A app.worker:celery_app worker -c 4 -Q bulk-messages

# Add more webhooks workers for high webhook volume
celery -A app.worker:celery_app worker -c 20 -Q webhooks
```

### 3. Use Autoscale for Demand Spikes

```bash
celery -A app.worker:celery_app worker --autoscale=10,3 -Q webhooks
# 10 max workers, 3 min workers
```

### 4. Monitor Queue Depth

Track queue lengths to trigger scaling:

| Queue | Normal Depth | Alert Threshold |
|-------|--------------|-----------------|
| `bulk-messages` | < 10 | > 50 |
| `webhooks` | < 100 | > 500 |
| `default` | < 20 | > 100 |

---

## Worker Configuration

### Campaign Worker

```bash
celery -A app.worker:celery_app worker \
  -c 4 \
  --max-tasks-per-child 1000 \
  --time-limit 3600 \
  --soft-time-limit 3300 \
  -Q bulk-messages,default \
  --loglevel=info
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `-c` (concurrency) | 4 | CPU-bound, prevent memory issues |
| `--max-tasks-per-child` | 1000 | Prevent memory leaks |
| `--time-limit` | 3600s | Max campaign runtime (1 hour) |
| `--soft-time-limit` | 3300s | Graceful shutdown before hard kill |

### Webhook Worker

```bash
celery -A app.worker:celery_app worker \
  -c 20 \
  --max-tasks-per-child 10000 \
  --time-limit 60 \
  --soft-time-limit 45 \
  -Q webhooks \
  --loglevel=warning
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `-c` (concurrency) | 20 | I/O-bound, handle high volume |
| `--max-tasks-per-child` | 10000 | Fast processing, higher threshold |
| `--time-limit` | 60s | Webhooks should be fast |
| `--soft-time-limit` | 45s | Timeout before HTTP client timeout |

### Import Worker

```bash
celery -A app.worker:celery_app worker \
  -c 2 \
  --max-tasks-per-child 100 \
  --time-limit 7200 \
  --soft-time-limit 6900 \
  -Q default \
  --loglevel=info
```

| Flag | Value | Rationale |
|------|-------|-----------|
| `-c` (concurrency) | 2 | Memory-intensive CSV processing |
| `--max-tasks-per-child` | 100 | Large memory footprint |
| `--time-limit` | 7200s | Imports can take hours |

---

## Database Connection Pooling

### Connection Pool Sizing

Each worker process needs DB connections:

```
Total connections = (worker_processes) × (concurrency per worker) × (connections per task)
```

### Recommended Pool Settings

| Worker Type | Concurrency | DB Connections Needed |
|-------------|-------------|----------------------|
| Campaign | 4 | 4-8 |
| Webhook | 20 | 2-4 |
| Import | 2 | 2-4 |

### Pool Configuration

```env
DATABASE_POOL_SIZE=10
DATABASE_MAX_OVERFLOW=20
DATABASE_POOL_TIMEOUT_SECONDS=30
```

---

## Memory Management

### Memory Limits

Set per worker to prevent runaway memory:

```bash
# Using systemd
[Service]
MemoryMax=1G
```

### Task Memory Usage

| Task | Memory per Task | Memory per 1000 Tasks |
|------|-----------------|----------------------|
| `campaign.send` | ~10MB | ~10GB (with batching) |
| `webhook.dispatch` | ~2MB | ~2GB |
| `contacts.import_job` | ~50MB | ~50GB |

### Prevent Memory Leaks

- `--max-tasks-per-child` to recycle workers
- Clear large objects after use
- Use streaming for large datasets

---

## Redis Connection Management

### Connection Pool

Each worker connects to Redis:

```bash
redis_url = redis://localhost:6379/0
```

### Connection Limits

| Setting | Value | Rationale |
|---------|-------|-----------|
| Max connections per worker | 10 | Prevent connection exhaustion |
| Socket timeout | 5s | Fast failure on Redis issues |

### Monitoring

Track Redis memory and connection count:
- `redis-cli info clients`
- `redis-cli info memory`

---

## Monitoring & Alerting

### Key Metrics

| Metric | Description | Alert |
|--------|-------------|-------|
| Queue depth | Tasks waiting | > threshold |
| Task latency | Time from queue to complete | > 95th percentile |
| Worker status | Active/idle/dead workers | any dead workers |
| Error rate | Failed tasks / total tasks | > 5% |
| Memory usage | Worker memory consumption | > 80% of limit |

### Monitoring Tools

1. **Flower**: Real-time Celery monitoring
   ```bash
   celery -A app.worker:celery_app flower
   ```

2. **Prometheus + Grafana**: Metrics aggregation
   - Export Celery metrics via celery-exporter
   - Dashboard for queue depths, task latency

3. **Health Checks**: Worker liveness
   ```
   GET /admin/queues/inspect
   ```

---

## Scaling Strategies

### Manual Scaling

```bash
# Add workers
celery -A app.worker:celery_app worker -c 4 -Q bulk-messages &

# Remove workers (graceful)
celery -A app.worker:celery_app control.shutdown
```

### Kubernetes Scaling

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: campaign-worker
spec:
  replicas: 2
  template:
    spec:
      containers:
        - name: worker
          command: ["celery", "-A", "app.worker:celery_app", "worker", "-c", "4", "-Q", "bulk-messages"]
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: webhook-worker
spec:
  replicas: 5
  template:
    spec:
      containers:
        - name: worker
          command: ["celery", "-A", "app.worker:celery_app", "worker", "-c", "20", "-Q", "webhooks"]
```

### HPA (Horizontal Pod Autoscaler)

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: webhook-worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: webhook-worker
  minReplicas: 2
  maxReplicas: 20
  metrics:
    - type: External
      external:
        metric:
          name: webhook_queue_depth
        target:
          type: AverageValue
          averageValue: "50"
```

---

## Task Acknowledgment

### Late Acknowledgment (acks_late=True)

Late acknowledgment ensures tasks are not lost if workers crash. The message is only removed from the queue after the task completes successfully.

```bash
# Late acknowledgment is now enabled globally in celery_app.py:
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)
```

**Why It Matters**:
| Without Late Ack | With Late Ack |
|----------------|---------------|
| Worker picks up task | Worker picks up task |
| Message ACK'd immediately | Worker executes task |
| Worker crashes | Task completes → ACK sent |
| Task LOST | Worker crashes → message requeued |
| | New worker picks up task |

**Task Categories**:

| Task Type | Late Ack | Visibility Timeout | Notes |
|-----------|----------|-------------------|-------|
| Webhook dispatch | Yes | 300s (5 min) | Fast I/O, high volume |
| Campaign send | Yes | 7200s (2 hours) | Long-running, checkabled |
| Contact import | Yes | 7200s (2 hours) | Batch processing |
| Segment materialize | Yes | 1800s (30 min) | DB-heavy |

### Crash Recovery Lifecycle

```
Worker Normal Operation:
  1. Worker picks task from queue
  2. Task executes
  3. On success: ACK sent → message removed
  4. On failure: NACK or retry → handled per task config

Worker Graceful Shutdown (SIGTERM):
  1. Worker stops accepting new tasks
  2. Completes in-flight tasks
  3. Sends ACK for completed tasks
  4. Remaining tasks requeued to broker
  5. Worker exits

Worker Crash (SIGKILL/OOM/Segfault):
  1. Worker process killed abruptly
  2. Message still in broker (not ACK'd)
  3. Visibility timeout expires (5 min default)
  4. Message returned to queue
  5. Another worker picks up task
  6. Idempotency check prevents duplicate execution
```

### Idempotency Guarantees

Every task with late acknowledgment MUST be idempotent:

| Task | Idempotency Mechanism |
|------|----------------------|
| `campaign.send` | Redis sent key + delivery_status check |
| `webhook.dispatch` | Ingestion status check + Redis idempotency |
| `contacts.import_job` | Job status check |
| `segments.materialize` | Segment membership REPLACE |

**Safe Task Pattern**:
```python
@celery_app.task(acks_late=True)
def safe_task(task_id):
    # 1. Check if already completed
    if is_already_done(task_id):
        return "already_completed"

    # 2. Do the work
    result = do_work()

    # 3. Mark as done only after success
    mark_as_done(task_id)
    return result
```

### Visibility Timeout

Redis broker uses visibility timeout to handle unacknowledged messages:

| Setting | Default | When to Increase |
|---------|---------|-----------------|
| `visibility_timeout` | 3600s (1 hour) | Long-running tasks exceed this |
| `task_acks_late` | True | Must be enabled for visibility timeout to matter |

**For Long-Running Campaigns**:
```python
# Set higher visibility timeout for campaign sends
# Note: This requires broker-specific config
broker_transport_options = {
    'visibility_timeout': 14400,  # 4 hours
}
```

---

## Future Enhancements

### Priority Queues

Different priorities for different task types:

```python
@celery_app.task(priority=5)
def process_campaign(...): ...

@celery_app.task(priority=9)
def process_webhook(...): ...
```

### Task Deduplication

Prevent duplicate task execution:

```python
@celery_app.task(
    dedup_timeout=3600,
    dedup_strategy="task-name"
)
def process_campaign(...): ...
```

### Distributed Tracing

OpenTelemetry integration:

```python
from opentelemetry import trace

tracer = trace.get_tracer(__name__)

@celery_app.task
def process_campaign(...):
    with tracer.start_as_current_span("campaign.send"):
        ...
```

### Worker Cost Optimization

Spot/preemptible instances for workers:
- Campaign workers: standard instances
- Webhook workers: spot instances (fault-tolerant)
- Import workers: on-demand (critical)
