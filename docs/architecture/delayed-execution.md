# Delayed Workflow Execution

> Delayed and scheduled workflow execution infrastructure. Last updated: 2026-05-13.

---

## Overview

The Delayed Execution System enables workflows to be scheduled and executed at a later time. It supports various delay types, timezone-aware scheduling, and ensures reliable execution with lease management and recovery mechanisms.

---

## Architecture

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Create    │───▶│  Schedule   │───▶│   Store     │
│   Request   │    │   Service   │    │   (DB)      │
└─────────────┘    └─────────────┘    └──────┬──────┘
                                             │
                                             ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   Workflow  │◀───│   Worker    │◀───│   Lease     │
│   Engine    │    │   (Queue)   │    │   Manager   │
└─────────────┘    └─────────────┘    └─────────────┘
       │
       ▼
┌─────────────┐
│   Metrics   │
└─────────────┘
```

---

## Delay Types

### 1. Fixed Delay
Execute after a fixed duration from creation.

```python
{
    "delay_type": "fixed",
    "config": {
        "duration_seconds": 3600  # 1 hour
    }
}
```

### 2. Relative Delay
Execute at a time relative to a field in the trigger data.

```python
{
    "delay_type": "relative",
    "config": {
        "field": "order_date",
        "offset_seconds": 86400,  # 1 day after order
        "fallback_seconds": 3600  # if field not present
    }
}
```

### 3. Wait Until
Execute at a specific timestamp.

```python
{
    "delay_type": "wait_until",
    "config": {
        "timestamp_field": "scheduled_time",
        "timezone": "America/New_York",
        "allow_past": true  # execute immediately if past
    }
}
```

### 4. Business Hours
Execute during business hours, respecting timezone.

```python
{
    "delay_type": "business_hours",
    "config": {
        "timezone": "America/New_York",
        "window_hours": 2
    }
}
```

---

## Execution Lifecycle

```
┌──────────┐     ┌──────────┐     ┌──────────┐     ┌──────────┐
│scheduled│────▶│ pending  │────▶│ running  │────▶│completed│
└──────────┘     └──────────┘     └──────────┘     └──────────┘
      │                │                │
      │                │                │
      ▼                ▼                ▼
  cancelled         failed          failed (retry)
      │                │                │
      ▼                ▼                ▼
  cancelled       expired         scheduled (retry)
```

### States

| State | Description |
|-------|-------------|
| `scheduled` | Created, waiting for scheduled time |
| `pending` | Ready to be processed, awaiting worker |
| `running` | Currently executing workflow |
| `completed` | Successfully completed |
| `failed` | Failed after max retries |
| `cancelled` | Manually cancelled |
| `expired` | Past validity window |

---

## Lease Management

### Purpose
Prevents duplicate execution when multiple workers attempt to process the same delayed execution.

### Flow
```
1. Worker picks up scheduled execution
2. Worker attempts to acquire lease (Redis + DB)
3. If lease acquired → mark as running, execute workflow
4. If lease not available → skip, let other worker handle
5. After execution → release lease
```

### Lease Configuration
- **Duration**: 5 minutes (configurable)
- **Storage**: PostgreSQL + Redis for fast lookup
- **Expiry**: Automatic expiration after timeout

---

## Recovery System

### Stale Execution Recovery
Detects executions stuck in `running` or `pending` state for too long (default: 10 minutes).

**Recovery Logic**:
1. Query executions where `updated_at < now - threshold`
2. If retries remaining → reset to `scheduled`
3. If max retries exceeded → mark as `failed`

### Lease Expiration
Periodically expires stale leases to allow other workers to pick up.

**Schedule**: Every 60 seconds

---

## Idempotency

### Duplicate Prevention
- **Idempotency Key**: Generated from `workspace_id + workflow_id + trigger_data + delay_config`
- **Database Constraint**: Prevents duplicate scheduled executions
- **API Response**: Returns 409 Conflict if duplicate exists

---

## Queue Configuration

### Queues

| Queue | Priority | Description |
|-------|----------|-------------|
| `delayed_execution` | High | Main processing queue |
| `delayed_recovery` | Medium | Stale execution recovery |
| `delayed_maintenance` | Low | Lease expiration |

### Celery Tasks

1. **ProcessScheduledDelayedTask**
   - Finds ready executions
   - Acquires lease
   - Executes workflow
   - Updates status

2. **RecoverStaleDelayedTask**
   - Detects stale executions
   - Reschedules or marks failed

3. **ExpireLeasesTask**
   - Expires old leases

---

## Metrics & Observability

### Tracked Metrics

| Metric | Description |
|--------|-------------|
| `delayed.total_scheduled` | Total scheduled |
| `delayed.completed` | Successfully completed |
| `delayed.failed` | Failed after retries |
| `delayed.running` | Currently executing |
| `delayed.avg_delay_seconds` | Average delay from schedule to start |

### Database Tables

1. **delayed_executions** - Execution schedules
2. **execution_leases** - Lease tracking
3. **business_hours_config** - Business hours settings
4. **delayed_execution_metrics** - Aggregated metrics

---

## API Endpoints

### Executions

| Method | Path | Description |
|--------|------|-------------|
| POST | `/delayed-executions` | Create delayed execution |
| GET | `/delayed-executions` | List executions |
| GET | `/delayed-executions/{id}` | Get execution |
| PATCH | `/delayed-executions/{id}` | Update execution |
| DELETE | `/delayed-executions/{id}` | Cancel execution |
| GET | `/delayed-executions/stats` | Statistics |

### Business Hours

| Method | Path | Description |
|--------|------|-------------|
| POST | `/business-hours` | Create business hours |
| GET | `/business-hours` | List business hours |
| DELETE | `/business-hours/{id}` | Delete business hours |

---

## Failure Recovery

### Worker Crash During Execution
1. Lease expires after 5 minutes
2. Recovery task detects stale execution
3. Execution rescheduled (if retries remain) or failed

### Database Failure
- Celery retries with exponential backoff
- Idempotency ensures no duplicate execution

### Network Timeout
- Task requeued by Celery (late acknowledgment enabled)
- Lease prevents duplicate execution

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DELAYED_LEASE_DURATION_SECONDS` | 300 | Lease duration |
| `DELAYED_STALE_THRESHOLD_MINUTES` | 10 | Stale detection |
| `DELAYED_BATCH_SIZE` | 50 | Processing batch |
| `DELAYED_MAX_RETRIES` | 3 | Max retries per execution |