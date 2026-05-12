# Event Lifecycle

> Domain events, naming conventions, and event taxonomy. Last updated: 2026-05-12.

---

## Overview

The platform uses a normalized event bus for tracking state changes and enabling downstream processing. Events are stored in `domain_events` table with workspace isolation.

---

## Event Naming Convention

Events follow a **verb.resource** pattern:

```
{action}.{resource}
```

| Component | Format | Example |
|-----------|--------|---------|
| Action | Past tense verb | `sent`, `created`, `updated` |
| Resource | Singular noun | `message`, `contact`, `campaign` |
| Separator | Dot | `.` |

---

## Event Taxonomy

### Message Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `message.sent` | Message dispatched to Meta API | `campaign_id`, `contact_id`, `message_id`, `provider_message_id` |
| `message.delivered` | Webhook: `delivered` status | `message_id`, `wamid`, `timestamp` |
| `message.read` | Webhook: `read` status | `message_id`, `wamid`, `timestamp` |
| `message.failed` | Webhook: `failed` or max retries | `message_id`, `wamid`, `error`, `failure_classification` |

### Contact Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `contact.created` | Contact upsert (import or API) | `contact_id`, `phone`, `source` |
| `contact.updated` | Contact update | `contact_id`, `changed_fields` |
| `contact.imported` | Import job completion | `job_id`, `total_rows`, `inserted`, `failed` |
| `contact.tag_added` | Tag assigned | `contact_id`, `tag_id`, `tag_name` |
| `contact.tag_removed` | Tag removed | `contact_id`, `tag_id` |
| `contact.note_added` | Note created | `contact_id`, `note_id` |
| `contact.note_deleted` | Note soft-deleted | `contact_id`, `note_id` |

### Campaign Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `campaign.created` | Campaign draft created | `campaign_id`, `template_id` |
| `campaign.started` | Campaign queued | `campaign_id`, `queued_job_id` |
| `campaign.completed` | All messages processed | `campaign_id`, `success_count`, `failed_count` |
| `campaign.failed` | Critical error during send | `campaign_id`, `error` |

### Segment Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `segment.created` | Segment definition created | `segment_id`, `name` |
| `segment.materialized` | Membership rebuild complete | `segment_id`, `membership_count` |
| `segment.archived` | Segment archived | `segment_id` |

### Webhook Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `webhook.received` | Incoming webhook ingested | `ingestion_id`, `source`, `event_type`, `trace_id` |
| `webhook.processed` | Webhook processing complete | `ingestion_id`, `action_taken` |
| `webhook.failed` | Webhook processing failed | `ingestion_id`, `error`, `retry_count` |

### Ecommerce Events

| Event | Trigger | Payload |
|-------|---------|---------|
| `order.created` | Shopify order webhook | `order_id`, `store_id`, `customer_phone`, `template_id` |
| `order.notification_sent` | Template message dispatched | `order_id`, `message_id`, `status` |

---

## Event Payload Standard

All events follow this base structure:

```json
{
  "event_id": "uuid",
  "event_type": "message.sent",
  "workspace_id": 1,
  "timestamp": "2026-05-12T10:00:00Z",
  "trace_id": "abc123",
  "payload": {
    // event-specific data
  }
}
```

### Required Fields

| Field | Type | Description |
|-------|------|-------------|
| `event_id` | UUID | Unique event identifier |
| `event_type` | string | Event name following naming convention |
| `workspace_id` | int | Workspace context |
| `timestamp` | ISO8601 | Event occurrence time |
| `trace_id` | string | Correlation ID for tracing |
| `payload` | object | Event-specific data |

---

## Event Lifecycle

### Ingestion
```
1. Action occurs in system
2. Service layer creates event
3. Event stored in domain_events table
4. Event published to queue (if async)
```

### Processing
```
1. Worker picks up event task
2. Downstream services react
3. Related entities updated
4. New events may be emitted
```

### Retention

- Events are append-only (no updates or deletes)
- Retention policy: configurable per workspace (future)
- Archival: cold storage for events older than 90 days (future)

---

## Trace ID Propagation

Trace IDs enable request tracing across async boundaries.

### Current Usage
- `trace_id` stored in `webhook_ingestions`
- Generated at webhook ingestion time
- Used for replay deduplication

### Standardized Propagation

All async tasks should accept and propagate `trace_id`:

```python
@celery_app.task(name="campaign.send")
def process_campaign_send_task(workspace_id, campaign_id, trace_id=None):
    if trace_id is None:
        trace_id = str(uuid4())
    # Use trace_id for logging and downstream calls
```

### Future Trace Pipeline
```
Request → Generate trace_id → Propagate to tasks → Log aggregation
                                   ↓
                          Correlation matrix
```

### Observability Integration (Planned)

- OpenTelemetry instrumentation
- Distributed tracing across workers
- Trace ID in all log lines
- Correlation dashboard

---

## Event Projections (Planned)

### Materialized Views

| Projection | Source Events | Refresh |
|-----------|--------------|---------|
| Contact activity feed | All `contact.*` events | Real-time |
| Campaign aggregates | `message.sent/delivered/read/failed` | On event |
| Delivery timeline | `message.*` events | On event |
| Segment membership | `contact.*` + segment.materialized | On materialization |

### Analytics Rollups (Planned)

- Hourly rollups: message counts by status
- Daily rollups: workspace usage totals
- Campaign summaries: success/failure breakdown
- Contact engagement scores

---

## Event Bus Architecture (Future)

```
┌─────────────┐
│   Sources   │
│ (API/Queue) │
└──────┬──────┘
       │
       ▼
┌─────────────┐
│  Event Bus  │  ← domain_events table + queue
└──────┬──────┘
       │
       ▼
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│ Handlers    │    │ Projections │    │ Analytics   │
│ (Workers)  │    │ (Read DB)   │    │ (Rollups)   │
└─────────────┘    └─────────────┘    └─────────────┘
```

### Event Bus Design Goals

- At-least-once delivery
- Idempotent handlers
- Backpressure handling
- Dead letter events
- Event replay from timestamp
