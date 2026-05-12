# Queue Topology

> How messages move through the system. Last updated: 2026-05-12.

---

## Queue Architecture

The platform uses a queue-first distributed execution model. Long-running tasks never execute inside request lifecycle.

```
API → Queue → Worker → Meta API
```

### Crash Safety

All tasks use **late acknowledgment** (task_acks_late=True). Messages are only removed from the queue after successful task completion. If a worker crashes, the message is automatically requeued after the visibility timeout expires.

---

## Active Queues

| Queue | Purpose | Routing |
|-------|---------|---------|
| `bulk-messages` | Bulk messaging execution | Default queue |
| `webhooks` | Webhook processing | Celery routing |
| `default` | Generic async jobs | Default routing |
| `retries` | Retry scheduling | Retry tasks |
| `dead-letter` | Failed jobs | DLQ handler |

### Queue Configuration

```python
# app/queue/celery_app.py
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="bulk-messages",
    task_create_missing_queues=True,
)
```

---

## Queue Tasks

### Core Tasks

| Task | Name | Purpose | Late Ack |
|------|------|---------|----------|
| `bulk.send_messages` | `bulk.send` | Async bulk send with batching | ✅ |
| `campaign.send` | `campaign.send` | Campaign execution with retry, idempotency, rate limiting | ✅ |
| `contacts.import_job` | `contacts.import_job` | CSV import processing | ✅ |
| `segments.materialize` | `segments.materialize` | Segment membership materialization | ✅ |

### Webhook Tasks

| Task | Name | Purpose | Late Ack |
|------|------|---------|----------|
| `webhook.dispatch` | `webhook.dispatch` | Process queued webhook dispatch | ✅ |

---

## Crash Recovery Lifecycle

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Worker Normal Operation                      │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Worker picks task from Redis broker                              │
│ 2. Task begins execution                                            │
│ 3. Task completes successfully                                      │
│ 4. ACK sent to broker → message removed from queue                    │
│ 5. Result stored in result backend                                   │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                         Worker Graceful Shutdown                    │
├─────────────────────────────────────────────────────────────────────┤
│ 1. SIGTERM received by worker                                       │
│ 2. Worker stops accepting new tasks                                  │
│ 3. Current tasks complete or wait for soft timeout                   │
│ 4. ACK sent for completed tasks                                     │
│ 5. Remaining tasks requeued to broker                                 │
│ 6. Worker exits cleanly                                             │
└─────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────┐
│                        Worker Crash / OOM / Kill                    │
├─────────────────────────────────────────────────────────────────────┤
│ 1. Worker process killed abruptly (SIGKILL, OOM, crash)              │
│ 2. Message remains in Redis broker (NOT acknowledged)                 │
│ 3. Visibility timeout starts (5 minutes default)                      │
│ 4. Visibility timeout expires                                        │
│ 5. Message returned to queue                                        │
│ 6. Another worker picks up task                                    │
│ 7. Idempotency check prevents duplicate execution                     │
│ 8. Task executes again (from checkpoint if available)               │
└─────────────────────────────────────────────────────────────────────┘
```

### Visibility Timeout

Redis broker tracks unacknowledged messages. If a message isn't ACK'd within the visibility timeout, it's returned to the queue.

| Scenario | Timeout | Behavior |
|----------|---------|----------|
| Normal execution | < 1 min | ACK sent on completion |
| Worker crash | 5 min (default) | Message requeued after timeout |
| Long task (>1 hour) | Must use task_acks_late | Message safe until completion |

---

## Task Routing Registry

Defined in `app/queue/registry.py`:

```python
celery_task_routes = {
    "campaign.send": {"queue": "bulk-messages"},
    "bulk.send": {"queue": "bulk-messages"},
    "contacts.import_job": {"queue": "default"},
    "segments.materialize": {"queue": "default"},
    "webhook.dispatch": {"queue": "webhooks"},
}
```

---

## Queue Features

### Retry Strategy
- Exponential backoff: `base_delay * 2^(attempt-1)`
- Max attempts configurable via `QUEUE_RETRY_MAX_ATTEMPTS`
- Error classification determines retryability:
  - `invalid_number`: no retry
  - `rate_limit`: retry with suggested delay
  - `api_error`: retry if `retryable=True`
  - `billing_error`: no retry

### Idempotency
- `queue:idempotency:inflight:{key}` — prevents concurrent sends
- `queue:idempotency:sent:{key}` — prevents duplicate sends
- TTLs configurable via env vars

### Rate Limiting
- Redis sliding window per workspace
- Configurable count/window via `QUEUE_WORKSPACE_RATE_LIMIT_*`
- Raises `WorkspaceRateLimitExceeded` with retry-after hint

### Dead Letter Queue
- Failed tasks after max retries stored in `queue_dead_letters`
- `QUEUE_DLQ_ENABLED=true` by default
- Admin endpoint: `GET /admin/queues/dead-letters`

### Replay Capabilities
- Dead letter records can be replayed
- Failed webhook ingestions replayable via `POST /admin/queues/webhook-ingestions/replay`
- Replay increments `retry_count`, sets `replayed_at`

---

## Worker Isolation Strategy

### Per-Queue Workers

Separate worker processes for operational isolation at scale:

| Worker | Queue(s) | Concurrency | Isolation Purpose |
|--------|----------|-------------|-------------------|
| Campaign Worker | `bulk-messages`, `default` | CPU-bound | Campaign execution, imports, segments |
| Webhook Worker | `webhooks` | I/O-bound | Fast webhook processing, dispatch |
| Retry Worker | `retries` | Low | Scheduled retries, cleanup |
| DLQ Worker | `dead-letter` | Very low | Failed job monitoring, alerting |

### Scaling Considerations

- Campaign workers: scale by CPU cores + memory (contact iteration)
- Webhook workers: scale by I/O throughput (fast HTTP processing)
- Add `--autoscale` for demand-based scaling
- Monitor via Flower or `GET /admin/queues/inspect`

### Concurrency Settings

```bash
# Campaign worker (heavy CPU)
celery -A app.worker:celery_app worker -c 4 -Q bulk-messages,default

# Webhook worker (fast I/O)
celery -A app.worker:celery_app worker -c 20 -Q webhooks

# Combined (development)
celery -A app.worker:celery_app worker --loglevel=info
```

---

## Message Lifecycle

```
1. API receives request
2. Task enqueued to Redis
3. Worker picks up task
4. Idempotency check (inflight key)
5. Rate limit check
6. Billing check
7. Execute operation (Meta API call)
8. Register result (tracking, events)
9. Mark idempotency (sent key)
10. Commit transaction
```

On failure:
```
1. Classify error (retryable?)
2. If retryable and attempts < max:
   - Sleep with backoff
   - Retry from step 4
3. If exhausted:
   - Store dead letter record
   - Mark delivery as failed
   - Update campaign aggregates
```

---

## Monitoring

- Worker inspect: `GET /admin/queues/inspect`
- Dead letters: `GET /admin/queues/dead-letters`
- Active tasks visible via Flower (future)
- Metrics pipeline planned for observability
