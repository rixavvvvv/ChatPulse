# Message Dispatch

> How messages flow from campaign to Meta API to tracking. Last updated: 2026-05-12.

---

## Overview

The dispatch system centralizes all WhatsApp message sending through a single service: `send_template_with_tracking()`. This ensures consistent behavior, retry logic, and tracking regardless of the send path.

---

## Dispatch Architecture

```
Campaign/Contact Import/API
         │
         ▼
   Queue Worker
         │
         ▼
  Dispatch Service
  send_template_with_tracking()
         │
    ┌────┴────┐
    ▼         ▼
 Meta API   Simulation
 (cloud)    Mode
    │
    ▼
Tracking Service
(register_sent_message)
    │
    ▼
Message Event
(record_message_event)
    │
    ▼
Analytics Aggregation
```

---

## Core Service: send_template_with_tracking()

Located in `app/services/message_dispatch_service.py`.

### Signature

```python
async def send_template_with_tracking(
    session: AsyncSession,
    *,
    workspace_id: int,
    phone: str,
    template_name: str,
    language: str,
    body_parameters: list[str] | None,
    header_parameters: list[str] | None,
    campaign_id: int | None,
    campaign_contact_id: int | None,
    contact_id: int | None,
    max_attempts: int | None = None,
) -> DispatchResult
```

### DispatchResult

```python
@dataclass(frozen=True, slots=True)
class DispatchResult:
    provider_message_id: str | None  # Meta's wamid
    retryable: bool                  # Can retry on failure
    error_message: str | None        # Human-readable error
    failure_classification: str | None  # invalid_number, rate_limit, api_error
```

---

## Send Paths

### Path 1: Campaign Send

```
POST /campaigns/{id}/queue
    ↓
campaign.send task
    ↓
send_template_with_tracking (per recipient)
    ↓
Meta API send
    ↓
register_sent_message → message_tracking table
    ↓
record_message_event → message_events table
    ↓
Update campaign aggregates
```

Features:
- Idempotency via Redis keys
- Per-workspace rate limiting
- Billing check before send
- Exponential retry with error classification

### Path 2: Bulk Send

```
POST /bulk-send/queue
    ↓
bulk.send task
    ↓
bulk_send_messages (batch)
    ↓
send_template_with_tracking (per contact)
    ↓
[Same as campaign send]
```

### Path 3: Shopify Order Webhook

```
POST /webhook/order-created
    ↓
HMAC verification
    ↓
send_template_with_tracking
    ↓
[Same as above]
    ↓
log to order_webhook_delivery_logs
```

### Path 4: Direct API Send (Planned)

```
POST /send-message
    ↓
Billing check
    ↓
send_template_with_tracking
    ↓
[Same as above]
```

---

## Provider Abstraction

Two providers supported:

### Cloud Provider (Production)

Calls Meta Graph API:
```
POST {base_url}/{version}/{phone_number_id}/messages
Authorization: Bearer {access_token}
```

### Simulation Provider (Development)

Returns mock response:
```python
{
    "message_id": f"mock_{uuid4().hex[:12]}"
}
```

Provider selected via `WHATSAPP_PROVIDER=cloud|simulation` env var.

---

## Template Parameters

Templates use Meta's numbered parameter format: `{{1}}`, `{{2}}`, etc.

### Build Process

`app/services/meta_template_params.py`:

```python
def build_numbered_template_parameters(text: str, name: str, phone: str) -> list[str]:
    # Pattern: {{N}} replaced with name/phone at specific positions
    # Returns list of [name, phone, ...] in template order
```

### Parameter Order Rules

- Header params extracted first
- Body params extracted second
- Only named placeholders replaced (`{{first_name}}`, `{{order_id}}`)
- Numbered placeholders filled by position

---

## Tracking System

### MessageTracking Table

Maps Meta's `wamid` to internal state:

| Field | Purpose |
|-------|---------|
| `provider_message_id` | Meta's wamid (unique) |
| `current_status` | sent/delivered/read/failed |
| `sent_at` | Dispatch timestamp |
| `delivered_at` | Webhook callback |
| `read_at` | Webhook callback |
| `failed_at` | Max retries or webhook |
| `last_webhook_payload` | Last status update |

### Tracking Flow

1. **Send**: Register `sent` status with `sent_at`
2. **Webhook**: Update status + timestamps
3. **Failure**: Mark `failed` + record error

### Webhook → Tracking Update

```
POST /webhook/meta
    ↓
Parse status (delivered/read/failed)
    ↓
Find message_tracking by wamid
    ↓
Update current_status + relevant timestamp
    ↓
Update last_webhook_at + payload
    ↓
Emit message event
```

---

## Error Handling

### Error Classifications

| Classification | Trigger | Retryable | Action |
|---------------|---------|-----------|--------|
| `invalid_number` | Phone validation fails | No | Mark failed immediately |
| `rate_limit` | Meta rate limit (429) | Yes | Retry with backoff |
| `api_error` | Meta API error (5xx) | Depends | Retry if retryable=True |
| `billing_error` | No quota remaining | No | Mark failed, notify user |

### Retry Logic

```python
def _retry_delay_seconds(attempt: int, base_delay: int) -> int:
    return base_delay * (2 ** max(0, attempt - 1))
```

Default: base_delay=2s, exponential backoff, max 4 attempts.

### Circuit Breaker (Planned)

Future: per-workspace circuit breaker after X consecutive failures.

---

## Rate Limiting

### Workspace-Level

Redis sliding window per workspace:

```
lua_script:
  ZREMRANGEBYSCORE key 0 (now - window)
  ZCARD key
  if count >= limit:
    reject
  else:
    ZADD key score=now
```

Configurable via:
- `QUEUE_WORKSPACE_RATE_LIMIT_COUNT`
- `QUEUE_WORKSPACE_RATE_LIMIT_WINDOW_SECONDS`

### Meta API Level

Respect `X-Business-Use-Case` rate limits from Meta responses.

---

## Delivery Analytics

### MessageEvent Table

Append-only event log:

| Event | Fields |
|-------|--------|
| sent | workspace_id, campaign_id, contact_id, status, timestamp |
| delivered | + message_tracking_id |
| read | + message_tracking_id |
| failed | + error, failure_classification |

### Aggregation Queries

```sql
-- Delivery rate by campaign
SELECT 
    campaign_id,
    COUNT(*) FILTER (WHERE status = 'sent') as sent,
    COUNT(*) FILTER (WHERE status = 'delivered') as delivered,
    COUNT(*) FILTER (WHERE status = 'read') as read,
    COUNT(*) FILTER (WHERE status = 'failed') as failed
FROM message_events
WHERE campaign_id = $1
GROUP BY campaign_id
```

---

## Future Enhancements

### Scheduled Sends
- `schedule_at` parameter on campaign queue
- Delayed task execution via Celery `eta`
- Scheduled tasks in separate queue

### Batch Optimization
- Aggregate sends within short windows
- Batch API calls to Meta (future Graph API support)
- Reduce connection overhead

### Multi-Provider
- Abstract provider interface
- Fallback providers (twilio, etc.)
- Provider-specific routing rules

### Template Variables
- Support full variable substitution
- Type coercion (dates, currency, etc.)
- Variable validation against template schema
