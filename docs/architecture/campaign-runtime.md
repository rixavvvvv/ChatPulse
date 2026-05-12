# Campaign Runtime

> How campaigns execute from queue to completion. Last updated: 2026-05-12.

---

## Overview

Campaigns are queued for async execution. The runtime handles idempotency, retries, rate limiting, billing checks, and status transitions.

---

## Campaign States

```
┌─────────┐     ┌─────────┐     ┌─────────┐     ┌────────────┐
│  draft  │────▶│ queued  │────▶│ running │────▶│ completed │
└─────────┘     └─────────┘     └─────────┘     └───────────┘
     │              │               │                 ▲
     │              │               │                 │
     │              │               ▼                 │
     │              │           ┌─────────┐           │
     │              └──────────▶│ failed  │───────────┘
     │                          └─────────┘
     ▼
 ┌─────────┐
 │archived │
 └─────────┘
```

### State Definitions

| State | Description |
|-------|-------------|
| `draft` | Campaign created, audience not bound |
| `queued` | Task enqueued to Celery |
| `running` | Worker actively processing recipients |
| `completed` | All recipients processed successfully |
| `failed` | Critical error or all sends failed |
| `archived` | Manually archived by user |

---

## Campaign Model

```python
class Campaign(Base):
    __tablename__ = "campaigns"
    
    id: Mapped[int]
    workspace_id: Mapped[int]
    template_id: Mapped[int | None]     # FK to templates
    name: Mapped[str]
    message_template: Mapped[str | None]  # Legacy direct template
    status: Mapped[str]                 # CampaignStatus enum
    queued_job_id: Mapped[str | None]   # Celery task ID
    success_count: Mapped[int]
    failed_count: Mapped[int]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### CampaignContact

Audience membership:

```python
class CampaignContact(Base):
    __tablename__ = "campaign_contacts"
    
    id: Mapped[int]
    workspace_id: Mapped[int]
    campaign_id: Mapped[int]
    source_contact_id: Mapped[int | None]  # FK to contacts
    idempotency_key: Mapped[str]           # For dedupe
    name: Mapped[str | None]
    phone: Mapped[str]
    delivery_status: Mapped[str]          # CampaignContactDeliveryStatus
    failure_classification: Mapped[str | None]
    attempt_count: Mapped[int]
    last_error: Mapped[str | None]
    created_at: Mapped[datetime]
```

---

## Execution Pipeline

### Step 1: Queue Campaign

```
POST /campaigns/{id}/queue
    │
    ▼
Validate campaign:
  - Template approved?
  - Template synced with Meta?
  - Audience not empty?
    │
    ▼
Update status: queued
    │
    ▼
Enqueue campaign.send task
    │
    ▼
Store celery_task_id in campaign.queued_job_id
    │
    ▼
Return: { job_id, status: "queued" }
```

### Step 2: Worker Execution

```
campaign.send task
    │
    ▼
Get campaign + template + audience
    │
    ▼
Update status: running
    │
    ▼
For each recipient in audience:
    │
    ├── Idempotency check (sent?)
    │     └── Skip if already sent
    │
    ├── Idempotency check (inflight?)
    │     └── Skip if currently sending
    │
    ├── Billing check
    │     └── Fail if quota exceeded
    │
    ├── Rate limit check
    │     └── Wait if rate limited
    │
    ├── Build template parameters
    │     └── Replace {{1}} placeholders
    │
    ├── Send via dispatch service
    │     └── send_template_with_tracking
    │
    ├── On success:
    │     ├── Mark delivery: sent
    │     ├── Increment campaign.success_count
    │     └── Mark idempotency: sent
    │
    └── On failure:
          ├── Classify error
          ├── Retry if retryable
          └── Or mark delivery: failed
    │
    ▼
Update status: completed/failed
```

### Step 3: Per-Recipient Retry Loop

```python
for attempt in range(max_attempts):
    try:
        dispatch = await send_template_with_tracking(...)
        if dispatch.error_message:
            raise RuntimeError(dispatch.error_message)
        # Success
        break
    except Exception as exc:
        classification, retryable = _classify_error(exc)
        if retryable and attempt < max_attempts - 1:
            delay = exponential_backoff(attempt)
            await asyncio.sleep(delay)
            continue
        # Failed permanently
        break
```

---

## Idempotency

### Why Idempotency Matters

Prevents duplicate sends when:
- Campaign re-queued after partial failure
- Worker crashes mid-execution
- Network timeout on dispatch

### Redis Keys

| Key Pattern | Purpose | TTL |
|------------|---------|-----|
| `queue:idempotency:sent:{key}` | Already sent | 7 days (`QUEUE_IDEMPOTENCY_TTL_SECONDS`) |
| `queue:idempotency:inflight:{key}` | Currently sending | 2 min (`QUEUE_INFLIGHT_TTL_SECONDS`) |

### Idempotency Key Format

```python
idempotency_key = f"campaign:{campaign_id}:contact:{contact_id}"
```

---

## Rate Limiting

### Workspace Rate Limit

Sliding window: max N messages per workspace per second.

```
┌─────────────────────────────────────────────────────┐
│ ZREMRANGEBYSCORE queue:rate_limit:{workspace} 0 t-1 │
│ ZCARD queue:rate_limit:{workspace}                  │
│ if count >= limit:                                  │
│   oldest = ZRANGE ... 0 0                           │
│   sleep until oldest expires                        │
│ ZADD queue:rate_limit:{workspace} {now}             │
└─────────────────────────────────────────────────────┘
```

Config:
- `QUEUE_WORKSPACE_RATE_LIMIT_COUNT` (default: 20)
- `QUEUE_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS` (default: 1)

---

## Billing Enforcement

### Check Points

| Check Point | Location |
|-------------|----------|
| Before campaign queue | `POST /campaigns/{id}/queue` |
| Before campaign execution | `campaign.send` task |
| Before per-recipient send | Inside worker loop |

### Check Logic

```python
async def ensure_workspace_can_send(
    session: AsyncSession,
    workspace_id: int,
    requested_count: int,
) -> None:
    # 1. Get workspace's subscription plan
    # 2. Get plan's message_limit
    # 3. Get workspace's usage for current cycle
    # 4. Check: usage + requested_count <= limit
    # 5. If exceeded, raise BillingLimitExceeded
```

### Quota Exhaustion

When quota exhausted:
- Campaign marked `failed`
- `last_error = "Billing limit exceeded"`
- Admin notified (future: email/push)
- Campaign cannot be re-queued until cycle resets

---

## Error Classification

### Classification Table

| Classification | Trigger | Retryable | Example |
|----------------|---------|----------|---------|
| `invalid_number` | Phone validation | No | Invalid phone format |
| `rate_limit` | Meta 429 / Workspace limit | Yes | Too many requests |
| `api_error` | Meta 5xx | Depends | Server error |
| `billing_error` | No quota | No | Limit exceeded |

### Handling by Classification

```python
if classification == "invalid_number":
    # No retry, mark failed immediately
    pass
elif classification == "rate_limit":
    # Retry with suggested delay
    suggested_delay = exc.retry_after_seconds
    await asyncio.sleep(suggested_delay)
elif classification == "api_error":
    if exc.retryable:
        # Retry with backoff
        pass
    else:
        # No retry, mark failed
        pass
```

---

## Status Updates

### Campaign Aggregate Updates

Inside worker loop, after each send:

```python
campaign.success_count = success_count
campaign.failed_count = failed_count
await session.commit()
```

For performance: commit after each batch (every N recipients).

### Final Status Transition

```python
if success_count > 0:
    await set_campaign_status(
        campaign,
        status=CampaignStatus.completed,
        success_count=success_count,
        failed_count=failed_count,
    )
else:
    await set_campaign_status(
        campaign,
        status=CampaignStatus.failed,
        success_count=0,
        failed_count=failed_count,
        last_error=failure_reasons[0] if failure_reasons else "All sends failed",
    )
```

---

## Progress Polling

### Endpoint

```
GET /campaigns/{id}/progress
Returns: {
  "status": "running",
  "total": 1000,
  "sent": 450,
  "failed": 20,
  "skipped": 5,
  "success_rate": 0.97
}
```

### Implementation

Query aggregate counts from `campaign_contacts`:

```sql
SELECT 
    delivery_status,
    COUNT(*) as count
FROM campaign_contacts
WHERE campaign_id = $1
GROUP BY delivery_status
```

---

## Campaign Scheduling (Planned)

### Schedule Endpoint

```python
POST /campaigns/{id}/queue
{
  "schedule_at": "2026-05-15T10:00:00Z"
}
```

### Implementation

Use Celery `eta` (estimated time of arrival):

```python
campaign.send.apply_async(
    args=[workspace_id, campaign_id],
    eta=schedule_at,  # Execute at scheduled time
)
```

### Scheduled Campaigns Queue

Separate queue for scheduled tasks:
- Lower concurrency
- Priority scheduling
- Monitoring for missed schedules

---

## Future Enhancements

### A/B Testing
- Multiple templates per campaign
- Random distribution to variants
- Conversion tracking per variant

### Time Window Targeting
- Send during business hours only
- Timezone-aware scheduling
- Max send rate over time window

### Personalization
- Contact attributes in templates
- Dynamic content per segment
- Conditional messages

### Drip Sequences (Planned)
- Multi-step campaigns
- Delay between steps
- Branching logic

### Campaign Analytics
- Engagement tracking
- Click tracking (future: buttons)
- Conversion attribution
