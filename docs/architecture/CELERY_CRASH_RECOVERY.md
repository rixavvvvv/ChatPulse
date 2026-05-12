# Celery Crash Recovery & Late Acknowledgment

> Comprehensive guide to task reliability, crash recovery, and idempotency. Last updated: 2026-05-12.

---

## Why Late Acknowledgment Matters

### The Problem with Early Acknowledgment

By default, Celery acknowledges messages **before** task execution. This creates a critical failure window:

```
Timeline with Early Acknowledgment:
───────────────────────────────────────────────────────────────
Worker receives task     Message ACK'd (removed from queue)    Worker starts executing
     │                              │                                   │
     ▼                              ▼                                   ▼
    [1] ─────────────────────────[2]────────────────────────────────[3]─►
                                                                      │
                                                              Worker CRASHES here
                                                                      │
                                                                      ▼
                                                                Task LOST forever
```

**Failure Scenarios**:
- Worker killed by OOM (Out of Memory)
- Worker killed by container restart
- Worker killed by SIGKILL
- Worker process crashes (segfault)
- Machine power failure

### The Solution: Late Acknowledgment

With `task_acks_late=True`, messages are only acknowledged **after** successful execution:

```
Timeline with Late Acknowledgment:
──────────────────────────────────────────────────────────────────────────────
Worker receives task     Worker starts executing     Task completes     ACK sent
     │                              │                       │              │
     ▼                              ▼                       ▼              ▼
    [1] ─────────────────────────[2]─────────────────────[3]──────────[4]─►
                                                                      │
                                                              Worker CRASHES here
                                                                      │
                                                                      ▼
                                                          Message NOT ACK'd
                                                          Redis requeues after 5min
                                                                      │
                                                                      ▼
                                                           New worker executes
                                                           (idempotency prevents duplicates)
```

---

## Configuration

### Global Settings

```python
# app/queue/celery_app.py
celery_app.conf.update(
    # CRITICAL: Late acknowledgment
    task_acks_late=True,

    # CRITICAL: Reject unacknowledged tasks when worker dies
    task_reject_on_worker_lost=True,

    # CRITICAL: Fair dispatch - one message per worker at a time
    worker_prefetch_multiplier=1,

    # Optional: Track task events for monitoring
    task_track_started=True,
    task_send_sent_event=True,
    worker_send_task_events=True,
)
```

### Why Each Setting Matters

| Setting | Purpose | Without It |
|---------|---------|------------|
| `task_acks_late=True` | ACK after completion, not before | Messages lost on crash |
| `task_reject_on_worker_lost=True` | Immediate requeue on worker death | Messages stuck until timeout |
| `worker_prefetch_multiplier=1` | Fair dispatch, one task per worker | Long tasks block fast ones |

---

## Crash Recovery Lifecycle

### 1. Normal Operation

```
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│  Redis   │─────▶│  Worker  │─────▶│  Task    │─────▶│  Redis   │
│  Broker  │      │  picks   │      │  Executes│      │  ACKs    │
└──────────┘      └──────────┘      └──────────┘      └──────────┘
                      │                                   │
                      └── Message removed from queue ──────┘
```

### 2. Graceful Shutdown (SIGTERM)

```
┌──────────┐      ┌──────────┐      ┌──────────┐      ┌──────────┐
│  SIGTERM │─────▶│  Stop    │─────▶│  Finish  │─────▶│  ACK &   │
│ received │      │  new     │      │  current │      │  Exit    │
└──────────┘      │  tasks   │      │  tasks   │      │  cleanly │
                   └──────────┘      └──────────┘      └──────────┘
                                      │
                                      └── Remaining tasks requeued
```

### 3. Worker Crash / OOM / SIGKILL

```
┌────────────────────────────────────────────────────────────────────────┐
│                              Worker Dies                                │
├────────────────────────────────────────────────────────────────────────┤
│ Redis Broker State:                                                     │
│   - Message still in queue (NOT acknowledged)                          │
│   - Message in "in-flight" state                                         │
│                                                                          │
│ Recovery Timeline:                                                       │
│   T+0min: Worker dies                                                    │
│   T+5min: Redis visibility timeout expires                               │
│   T+5min: Message returned to queue                                      │
│   T+5min: New worker picks up task                                        │
│   T+5min: Idempotency check passes                                       │
│   T+5min: Task re-executes                                               │
└────────────────────────────────────────────────────────────────────────┘
```

### 4. Container Restart (Kubernetes/Docker)

```
┌────────────────────────────────────────────────────────────────────────┐
│                         Container/Orchestrator Restart                  │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Old container killed → all workers die                               │
│ 2. All messages in-flight return to Redis broker (not acknowledged)     │
│ 3. Visibility timeout starts (5 minutes)                                 │
│ 4. New container starts → new workers spawn                              │
│ 5. Messages requeued as visibility timeout expires                      │
│ 6. New workers pick up tasks                                              │
│ 7. Idempotency prevents duplicate execution                              │
└────────────────────────────────────────────────────────────────────────┘
```

---

## Idempotency: Preventing Duplicate Execution

Late acknowledgment enables "at-least-once" delivery, not "exactly-once". This means tasks may execute multiple times after crashes. **Idempotency is mandatory.**

### Idempotency Mechanisms

| Level | Mechanism | Scope |
|-------|-----------|-------|
| Task-level | Redis idempotency key | Per task invocation |
| Record-level | Database status check | Per business entity |
| Constraint-level | Unique constraints | Per entity instance |

### Task Idempotency Pattern

```python
# NOT IDEMPOTENT - Will send multiple messages!
@celery_app.task(acks_late=True)
def unsafe_send_message(phone, message):
    send_whatsapp_message(phone, message)  # Sends every time!
    return "sent"

# IDEMPOTENT - Safe to retry
@celery_app.task(acks_late=True)
def safe_send_message(phone, message):
    # 1. Check if already sent
    if was_already_sent(phone):
        return "already_sent"

    # 2. Do the work
    result = send_whatsapp_message(phone, message)

    # 3. Only mark after success
    mark_as_sent(phone)
    return "sent"
```

### Implemented Idempotency

| Task | Idempotency Check | Implementation |
|------|-------------------|-----------------|
| `campaign.send` | Redis `sent` key + `delivery_status` | `queue:idempotency:sent:{key}` |
| `webhook.dispatch` | Ingestion status check + Redis key | `processing_status == completed` |
| `contacts.import_job` | Job status check | `job.status == 'processing'` |
| `segments.materialize` | Membership REPLACE | `DELETE + INSERT` pattern |

---

## Safe Transaction Boundaries

### The Problem

Long-running tasks that modify database state need careful transaction handling. If a worker crashes mid-transaction, data may be partially committed.

### Safe Pattern: Commit After Complete Success

```python
async def safe_campaign_send(workspace_id, campaign_id):
    redis = Redis.from_url(settings.redis_url)

    try:
        async with AsyncSessionLocal() as session:
            # 1. Read all data needed
            campaign = await get_campaign(session, campaign_id)
            template = await get_template(session, campaign.template_id)

            # 2. Begin transaction
            async with session.begin():
                # 3. Do all work
                for contact in contacts:
                    await send_message(session, contact)
                    update_progress(campaign)

                # 4. Commit only after ALL work complete
                await session.commit()

            # 5. Now ACK is safe (task completed)

    finally:
        await redis.aclose()
```

### Unsafe Pattern: Partial Commits

```python
# NOT SAFE - Commits after each contact
for contact in contacts:
    await send_message(session, contact)
    await session.commit()  # ACK'd after first commit
    # If worker crashes here, rest of contacts not processed
```

### Campaign Send Safe Pattern

The campaign send task uses safe commit patterns:

```python
# app/queue/tasks.py

async def _run_campaign_send(workspace_id, campaign_id):
    redis = Redis.from_url(settings.redis_url)

    try:
        async with AsyncSessionLocal() as session:
            # 1. Load all data upfront
            campaign = await get_campaign(session, campaign_id)
            audience = await load_audience(session, campaign_id)

            # 2. Update status atomically
            await set_campaign_status(session, campaign, 'running')

            for contact in audience:
                # IDEMPOTENCY CHECK
                if await _already_sent(redis, contact.idempotency_key):
                    continue

                # 3. Do the work
                await send_template_with_tracking(session, contact)

                # 4. Batch commit every N contacts (for performance)
                if contact_index % 100 == 0:
                    await session.commit()

            # 5. Final commit
            await session.commit()
            await set_campaign_status(session, campaign, 'completed')

    finally:
        await redis.aclose()
```

---

## Visibility Timeout Strategy

### What is Visibility Timeout?

When Redis brokers a message, it's in "visible" state. If not acknowledged within visibility timeout, Redis requeues it.

```
Without visibility timeout:
  Worker picks message → Worker crashes → Message lost forever

With visibility timeout (5 min):
  Worker picks message → 5 min passes → Not ACK'd → Requeued → New worker picks up
```

### Configuring Visibility Timeout

```python
# For Redis broker
broker_transport_options = {
    'visibility_timeout': 3600,  # 1 hour (for long tasks)
}
```

### Recommended Settings by Task Type

| Task Type | Visibility Timeout | Rationale |
|-----------|-------------------|-----------|
| Webhooks | 300s (5 min) | Fast processing |
| Notifications | 300s (5 min) | Fast processing |
| Bulk sends | 7200s (2 hours) | May process 1000s of contacts |
| Imports | 7200s (2 hours) | Large CSV files |
| Segment materialization | 3600s (1 hour) | Complex queries |

---

## Worker Scaling for Reliability

### Separate Queues for Different Task Types

```bash
# Campaign worker - handles long-running tasks
celery -A app.worker:celery_app worker \
  -c 4 \
  -Q bulk-messages \
  --time-limit=7200 \
  --soft-time-limit=6900

# Webhook worker - handles fast I/O
celery -A app.worker:celery_app worker \
  -c 20 \
  -Q webhooks \
  --time-limit=60 \
  --soft-time-limit=45
```

### Why Prefetch Multiplier = 1

```bash
# WRONG: prefetch_multiplier=4
# Worker pre-fetches 4 messages
# Crashes while processing #3
# Message #4 stuck until timeout

# CORRECT: prefetch_multiplier=1
# Worker fetches 1 message at a time
# Crashes → Message #1 requeued immediately
# Other messages still in queue
```

---

## Monitoring & Alerting

### Key Metrics to Watch

| Metric | Description | Alert Threshold |
|--------|-------------|-----------------|
| `worker.dead` | Workers that died | > 0 |
| `task.late_ack.rejected` | Tasks rejected on worker death | > 5/hour |
| `task.acks_late.count` | Total late-ACK tasks | N/A |
| `queue.depth` | Messages waiting | > 100 |
| `task.latency` | Time in queue before execution | > 5 min |

### Prometheus Metrics (Future)

```python
from celery.events import Events

@app.task
def export_stats():
    # Export to Prometheus:
    # - celery_tasks_total{status="ack_late"}
    # - celery_worker_events{event="worker-down"}
    pass
```

---

## Testing Crash Recovery

### Test 1: Worker Kill During Task

```python
import signal
import subprocess

def test_worker_crash_recovery():
    # Start worker
    worker = subprocess.Popen(['celery', '-A', 'app.worker', 'worker'])

    # Enqueue task
    result = process_campaign_send_task.delay(workspace_id=1, campaign_id=1)

    # Wait for task to start
    time.sleep(2)

    # Kill worker
    worker.send_signal(signal.SIGKILL)

    # Wait for visibility timeout
    time.sleep(310)  # 5 min + buffer

    # Check task was retried
    task = AsyncResult(result.id)
    assert task.state in ['PENDING', 'STARTED', 'SUCCESS']
```

### Test 2: Idempotency After Crash

```python
def test_idempotency_after_crash():
    # Enqueue task that partially completes
    task_id = process_campaign_send_task.delay(
        workspace_id=1,
        campaign_id=1,
        contact_id=1
    )

    # Wait for idempotency check to pass
    time.sleep(1)

    # Simulate crash and retry
    # Task should skip already-sent contacts
    result = wait_for_result(task_id, timeout=120)

    assert result.info['skipped'] > 0
```

---

## Troubleshooting

### Issue: Tasks Not Requeuing

**Symptoms**: Worker dies, tasks don't requeue

**Diagnosis**:
```bash
# Check if task_acks_late is enabled
celery -A app.worker:celery_app inspect conf | grep task_acks_late

# Check broker connection
celery -A app.worker:celery_app inspect stats
```

**Solutions**:
1. Ensure `task_acks_late=True` in config
2. Ensure `task_reject_on_worker_lost=True`
3. Check broker (Redis) is running

### Issue: Duplicate Task Execution

**Symptoms**: Tasks executing multiple times

**Diagnosis**:
```bash
# Check idempotency keys
redis-cli KEYS "celery:task:executed:*"
```

**Solutions**:
1. Verify idempotency checks are in place
2. Add Redis idempotency key per task invocation
3. Check database unique constraints

### Issue: Tasks Stuck in Queue

**Symptoms**: Tasks queue but never execute

**Diagnosis**:
```bash
# Check worker status
celery -A app.worker:celery_app inspect active

# Check for task errors
celery -A app.worker:celery_app events
```

**Solutions**:
1. Workers may be overwhelmed (increase workers)
2. Tasks may have long time limits
3. Visibility timeout may need adjustment

---

## Checklist: Before Enabling Late ACK

- [ ] All tasks have idempotency checks
- [ ] All tasks handle duplicate execution gracefully
- [ ] `task_acks_late=True` configured globally
- [ ] `task_reject_on_worker_lost=True` configured
- [ ] `worker_prefetch_multiplier=1` configured
- [ ] Long-running tasks have checkpoints
- [ ] DLQ persistence configured for failed tasks
- [ ] Visibility timeout set appropriately per task type
- [ ] Monitoring in place for worker crashes
- [ ] Tests verify crash recovery behavior
