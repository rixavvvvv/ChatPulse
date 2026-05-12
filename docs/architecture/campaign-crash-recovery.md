# Campaign Execution Recovery Architecture

Crash recovery system for campaign execution with heartbeat monitoring, execution leases, and safe resume points.

## Overview

Campaigns can fail due to various infrastructure issues:
- Worker crashes (OOM, SIGKILL, container restart)
- Network partitions
- Database connection failures
- Stuck execution loops

This system detects stalled campaigns and recovers them to their last safe checkpoint without duplicate sends.

## Key Components

### 1. Heartbeat System

Workers report liveness via Redis heartbeats:

```
Worker                          Redis
   |                               |
   |---SET campaign:heartbeat:123->|
   |    {"task_id": "abc",         |
   |     "timestamp_ms": 123...}   |
```

**Heartbeat Contents:**
- `campaign_id`: Campaign being processed
- `task_id`: Celery task ID
- `timestamp_ms`: Unix timestamp in milliseconds
- `metadata`: Progress info (processed, total, etc.)

**TTL**: 3x stale threshold (default 9 minutes)
- Sufficient for worker to heartbeat before expiry
- Auto-cleans if worker crashes completely

### 2. Execution Lease

Redis-based distributed lock ensuring only one worker processes a campaign:

```
Worker A                      Worker B                    Redis
   |                              |                          |
   |---SETNX lease:123=worker-A-->|                          |
   |   (OK)                       |                          |
   |                              |---SETNX lease:123=worker-B
   |                              |    (fail - exists)        |
   |                              |   <- fail               |
```

**Lease Properties:**
- **TTL**: 5 minutes (worker must heartbeat within this time)
- **Atomic**: SETNX ensures only one holder
- **Renewable**: Worker can extend its own lease
- **Safe Release**: Lua script ensures only owner can release

### 3. Stale Campaign Detection

Periodic task scans for campaigns that need recovery:

```
Recovery Worker
      |
      |---SELECT * FROM campaigns
      |    WHERE status = 'running'
      |    AND last_heartbeat_at < now - 3min
      |
      |<-- [campaigns with stale heartbeats]
```

**Detection Criteria:**
1. Status = `running`
2. `last_heartbeat_at` > 3 minutes ago
3. Celery task no longer active (verified via inspector)

### 4. Recovery Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                        RECOVERY FLOW                                 │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  1. DETECT                                                           │
│     ┌──────────────────┐                                              │
│     │ Find stalled     │  - running status                           │
│     │ campaigns        │  - stale heartbeat                          │
│     └────────┬─────────┘  - inactive celery task                    │
│              │                                                        │
│              ▼                                                        │
│  2. LOCK                                                             │
│     ┌──────────────────┐                                              │
│     │ Acquire recovery │  - Redis SETNX (10min TTL)                 │
│     │ lock             │  - Prevents concurrent recovery             │
│     └────────┬─────────┘                                              │
│              │                                                        │
│              ▼                                                        │
│  3. ANALYZE                                                          │
│     ┌──────────────────┐                                              │
│     │ Find safe resume │  - Last sent contact ID                     │
│     │ point            │  - Skip already sent/failed                 │
│     └────────┬─────────┘                                              │
│              │                                                        │
│              ▼                                                        │
│  4. RESET                                                             │
│     ┌──────────────────┐                                              │
│     │ Reset pending    │  - Mark pending contacts as ready           │
│     │ recipients       │  - Clear attempt counts                     │
│     └────────┬─────────┘                                              │
│              │                                                        │
│              ▼                                                        │
│  5. REQUEUE                                                           │
│     ┌──────────────────┐                                              │
│     │ Schedule new     │  - New Celery task                          │
│     │ send task        │  - Idempotency ensures no dups               │
│     └──────────────────┘                                              │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

## Crash Recovery Lifecycle

### Normal Execution

```
Time    Worker A                          Database           Redis
  │        │                                 │                 │
  │        │ BEGIN transaction               │                 │
  │        |-------------------------------->│                 |
  │        │                                 │                 |
  │        | SET campaign:lease:123=worker-A │                 │
  │        | EXPIRE 300                      │                 |
  │        |------------------------------------------------>|
  │        |                                 │                 |
  │        | SET campaign:heartbeat:123      │                 |
  │        |------------------------------------------------>|
  │        |                                 │                 |
  │   [Process contacts...]                  │                 │
  │        |                                 │                 |
  │        | SET campaign:heartbeat:123      │ (every 30s)     │
  │        |------------------------------------------------>|
  │        |                                 │                 |
  │        | SET campaign:heartbeat:123      │ (every 30s)     │
  │        |------------------------------------------------>|
  │        |                                 │                 |
  │        | UPDATE campaign SET status=completed            │
  │        |------------------------------------------------>│
  │        |                                 │                 |
  │        | DEL campaign:lease:123          │                 |
  │        | DEL campaign:heartbeat:123      │                 |
  │        |------------------------------------------------>|
  │        |                                 │                 │
  │        | COMMIT                          │                 │
  │        |------------------------------------------------>|
```

### Worker Crash During Execution

```
Time    Worker A                          Database           Redis
  │        │                                 │                 │
  │   [Worker crashes - OOM, SIGKILL, etc.] │
  │        X                                 │                 │
  │        │                                 │                 │
  │        │                                 │  (lease expires │)
  │        |                                 │   after 5 min)  │
  │        |                                 │                 │
  │        |       Recovery Worker            │                 │
  │        |              │                   │                 │
  │        |              | SELECT stalled    │                 │
  │        |              |---------------------------->|
  │        |              |                   │                 |
  │        |              | GET heartbeat     │                 │
  │        |              | (stale/expired)   │                 |
  │        |              |---------------------------->|
  │        |              |                   │                 │
  │        |              | Acquire recovery  │                 │
  │        |              | lock              │                 │
  │        |              |---------------------------->|
  │        |              |                   │                 │
  │        |              | Find last sent   │                 │
  │        |              | contact           │                 |
  │        |              |---------------------------->|
  │        |              |                   │                 │
  │        |              | Reset pending    │                 │
  │        |              | contacts         │                 │
  │        |              |---------------------------->|
  │        |              |                   │                 │
  │        |              | Schedule new task│                 │
  │        |              |---------------------------->|
  │        |              |                   │                 │
  │        |      Worker B                    │                 │
  │        |              │                   │                 │
  │        |        BEGIN transaction        │                 │
  │        |        (resumes from checkpoint)│                 |
```

## Resume Guarantees

### At-Least-Once Delivery

The system guarantees each contact is processed at least once:

1. **Idempotency Keys**: Each contact has a unique idempotency key
   - `campaign:{id}:contact:{contact_id}`
   - If sent, key exists in Redis with TTL

2. **Status Check**: Before sending, check `delivery_status` in DB
   - `sent` → skip
   - `failed` → retry (if attempts remain)
   - `pending` → process

3. **In-Flight Lock**: Prevents concurrent processing
   - SETNX on `inflight:{idempotency_key}`
   - Blocks duplicate workers

### Safe Resume Point

Resume point is determined by the last successfully SENT contact:

```python
async def _determine_safe_resume_point(campaign_id):
    # Find last sent contact
    last_sent = await db.query(
        "SELECT id FROM campaign_contacts "
        "WHERE campaign_id = ? "
        "AND delivery_status = 'sent' "
        "ORDER BY id DESC LIMIT 1"
    )

    # Resume from next contact after last sent
    return last_sent.id + 1
```

**Why this is safe:**
- All contacts before `last_sent.id` are confirmed delivered
- Contacts after are either pending or not yet attempted
- No gap between confirmed and to-be-processed

### Failure Handling Strategy

| Failure Type | Detection | Recovery Action |
|-------------|-----------|-----------------|
| Worker OOM | Lease expiry | Requeue remaining contacts |
| Worker SIGKILL | Lease expiry | Requeue remaining contacts |
| Network partition | Heartbeat stale | Requeue remaining contacts |
| Database down | Recovery task fails | Retry with backoff |
| Redis down | All operations fail | Fall back to DB-only mode |
| Stuck loop | Heartbeat stale | Terminate and requeue |

### Recovery States

```
                    ┌─────────────────┐
                    │     draft       │
                    └────────┬────────┘
                             │ launch
                             ▼
                    ┌─────────────────┐
            ┌───────│     queued      │──────┐
            │       └─────────────────┘      │
            │ start task                     │ error
            ▼                                ▼
   ┌─────────────────┐            ┌─────────────────┐
   │     running      │            │     failed       │
   └────────┬────────┘            └─────────────────┘
            │
    ┌───────┴───────┐
    │               │
heartbeat          heartbeat
stale              recent
    │               │
    ▼               ▼
┌─────────┐   ┌─────────────────┐
│stalled? │──>│  recovering      │
└────┬────┘   └────────┬─────────┘
     │                 │
     │ recovery        │ complete
     │ complete        │
     ▼                 ▼
[resumes from     ┌─────────────────┐
 checkpoint]      │    completed     │
                  └─────────────────┘
```

### Recovery Limits

- **Max concurrent recoveries**: 5 (configurable)
- **Recovery lock TTL**: 10 minutes
- **Recovery task retry**: 5 attempts with exponential backoff
- **Stale threshold**: 3 minutes (configurable)

## Metrics and Audit

### Recovery Metrics (Redis)

```
ratelimit:metrics:recovery
├── detected: 15          # Campaigns detected as stalled
├── recovered: 12         # Successfully recovered
├── failed: 3             # Recovery attempts that failed
└── last_run: 1704067200  # Unix timestamp
```

### Audit Log Events

```python
# Domain events recorded for each recovery
DomainEvent(
    event_type="campaign.recovery.detected",
    payload={
        "campaign_id": 123,
        "reason": "no_heartbeat_and_task_not_active",
        "stale_duration_seconds": 300,
    }
)

DomainEvent(
    event_type="campaign.recovery.started",
    payload={
        "campaign_id": 123,
        "resume_index": 456,
        "reset_count": 50,
    }
)

DomainEvent(
    event_type="campaign.recovery.completed",
    payload={
        "campaign_id": 123,
        "new_task_id": "abc123",
        "previous_success_count": 100,
    }
)
```

## Configuration

```python
# In settings
queue_stale_campaign_threshold_seconds = 180  # 3 minutes
queue_recovery_lock_ttl_seconds = 600         # 10 minutes
queue_heartbeat_interval_seconds = 30          # 30 seconds
queue_lease_ttl_seconds = 300                  # 5 minutes
```

## Monitoring Recommendations

Key metrics to track:
- `campaign.recovery.detected` - Rate of stalled campaigns
- `campaign.recovery.duration` - Time to recover
- `campaign.recovery.duplicate_sends` - Counter (should be 0)
- `campaign.lease.conflicts` - Lease acquisition failures

Alert thresholds:
- Stalled campaigns > 5 per minute
- Recovery duration P99 > 30 seconds
- Any duplicate sends detected

## Testing Strategy

See `tests/queue/test_campaign_recovery.py`:

1. **Lease tests**: Acquire, renew, release, conflict handling
2. **Heartbeat tests**: Record, check staleness, TTL behavior
3. **Detection tests**: Find stale campaigns, exclude active ones
4. **Recovery tests**: Full recovery flow, idempotency
5. **Edge cases**: Zero recipients, Redis failures, etc.