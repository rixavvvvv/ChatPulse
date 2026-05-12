# Database Boundaries

> Ownership, transactional rules, and cross-service access patterns. Last updated: 2026-05-12.

---

## Overview

Multiple workers can touch the same tables concurrently. Clear ownership boundaries prevent race conditions, deadlocks, and inconsistent state.

---

## Table Ownership by Bounded Context

### Contact Intelligence

| Table | Primary Owner | Write Boundary |
|-------|--------------|-----------------|
| `contacts` | `ContactService` | Single workspace |
| `tags` | `TagService` | Single workspace |
| `contact_tags` | `TagService` | Single workspace |
| `attribute_definitions` | `ContactAttributeService` | Single workspace |
| `contact_attribute_values` | `ContactAttributeService` | Single workspace |
| `contact_notes` | `ContactNoteService` | Single workspace |
| `contact_activities` | `ContactActivityService` | Single workspace |
| `contact_import_jobs` | `ContactImportService` | Single workspace |
| `contact_import_rows` | `ContactImportService` | Single workspace |
| `segments` | `SegmentService` | Single workspace |
| `segment_memberships` | `SegmentService` | Single workspace |

### Messaging Infrastructure

| Table | Primary Owner | Write Boundary |
|-------|--------------|-----------------|
| `templates` | `TemplateService` | Single workspace |
| `campaigns` | `CampaignService` | Single workspace |
| `campaign_contacts` | `CampaignService` | Single workspace |
| `message_events` | `MessageEventService` | Single workspace |
| `message_tracking` | `MessageDispatchService` | Single workspace |

### Queue Infrastructure

| Table | Primary Owner | Write Boundary |
|-------|--------------|-----------------|
| `webhook_ingestions` | `WebhookIngestionService` | Single workspace |
| `domain_events` | `DomainEventService` | Single workspace |
| `queue_dead_letters` | `QueueMonitoringService` | Global |

### Meta Integration

| Table | Primary Owner | Write Boundary |
|-------|--------------|-----------------|
| `meta_credentials` | `MetaCredentialService` | Single workspace |

### Ecommerce

| Table | Primary Owner | Write Boundary |
|-------|--------------|-----------------|
| `ecommerce_store_connections` | `EcommerceStoreService` | Single workspace |
| `ecommerce_event_template_maps` | `EcommerceTemplateMapService` | Single workspace |
| `order_webhook_delivery_logs` | `OrderWebhookService` | Single workspace |

---

## Write Boundary Rules

### Rule 1: One Writer Per Entity Type

Only one service should write to a given table within a workspace:

```
✅ CampaignService writes to campaigns
✅ CampaignService writes to campaign_contacts
❌ BulkService should NOT write to campaigns
❌ WebhookService should NOT write to campaign_contacts
```

### Rule 2: Idempotent Writes

All writes should be idempotent to handle retries:

```python
# Bad: Duplicate inserts on retry
INSERT INTO contacts (workspace_id, phone) VALUES (1, '123')

# Good: Upsert pattern
INSERT INTO contacts (workspace_id, phone, ...)
VALUES (1, '123', ...)
ON CONFLICT (workspace_id, phone) DO UPDATE SET ...
```

### Rule 3: Optimistic Concurrency for Critical Updates

Use version columns or explicit locking for state transitions:

```python
# Campaign status transition
UPDATE campaigns
SET status = 'running', updated_at = NOW()
WHERE id = :id AND status = 'queued'
RETURNING id
-- If no rows affected, transition already happened
```

---

## Cross-Service Access Rules

### Read Access Patterns

| Reader | Tables Read | Notes |
|--------|------------|-------|
| `CampaignService` | `campaigns`, `templates`, `campaign_contacts`, `contacts` | Read-only during execution |
| `MessageDispatchService` | `message_tracking`, `message_events`, `meta_credentials` | Tracking lookups |
| `WebhookService` | `webhook_ingestions`, `message_tracking`, `domain_events` | Status updates |
| `SegmentService` | `contacts`, `tags`, `contact_tags`, `attribute_definitions`, `contact_attribute_values`, `segment_memberships` | Materialization reads |
| `AnalyticsService` | `message_events`, `campaigns`, `usage_tracking` | Aggregation reads |

### Write Access Patterns

| Writer | Tables Written | Triggers |
|--------|----------------|----------|
| `CampaignService` | `campaigns`, `campaign_contacts` | Campaign execution |
| `MessageDispatchService` | `message_tracking`, `message_events` | On send, on webhook |
| `WebhookService` | `webhook_ingestions`, `domain_events` | On webhook receive |
| `ContactImportService` | `contacts`, `contact_import_jobs`, `contact_import_rows` | CSV import |
| `ContactActivityService` | `contact_activities` | On contact events |

### Forbidden Access Patterns

```
❌ Queue workers should NEVER write to domain_events directly
   → Use DomainEventService from within business logic

❌ WebhookService should NEVER update campaign aggregates
   → Only update message_tracking, let campaign polling refresh

❌ CampaignService should NEVER create contact_activities
   → ContactActivityService handles this

❌ BulkService should NEVER touch segment_memberships
   → SegmentService owns this table
```

---

## Transactional Boundaries

### Unit of Work Pattern

Each service operation should be atomic:

```python
async def campaign_send(workspace_id, campaign_id):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            # All writes in single transaction
            await update_campaign_status(session, campaign_id, 'running')
            await send_messages(session, campaign_id)
            await update_campaign_status(session, campaign_id, 'completed')
```

### Cross-Domain Transactions

Avoid cross-domain transactions. Instead, use event-driven eventual consistency:

```
❌ Bad: Single transaction spanning messaging + contact intelligence
BEGIN
  UPDATE contacts SET last_contacted = NOW() WHERE id = ...
  INSERT INTO message_tracking (...) VALUES (...)
COMMIT

✅ Good: Separate transactions with event bridge
BEGIN
  INSERT INTO message_tracking (...) VALUES (...)
COMMIT

-- Event-driven trigger
BEGIN
  UPDATE contacts SET last_contacted = NOW() WHERE id = ...
COMMIT
```

### Session-per-Request Pattern

```python
# API layer
async def route_handler(session: AsyncSession = Depends(get_db_session)):
    await service.operation(session, ...)
    await session.commit()  # Explicit commit at route level
```

### Worker Transaction Pattern

```python
# Queue workers
async def queue_task(workspace_id, campaign_id):
    async with AsyncSessionLocal() as session:
        async with session.begin():
            await campaign_service.execute(session, workspace_id, campaign_id)
        # Auto-commit on success, rollback on exception
```

---

## Eventual Consistency Expectations

### Immediate Consistency (Synchronous)

| Operation | Tables | Lag |
|----------|--------|-----|
| Create contact | `contacts` | 0ms |
| Update contact | `contacts` | 0ms |
| Create campaign | `campaigns` | 0ms |
| Queue campaign | `campaigns` | 0ms |

### Near-Real-Time (Async, <1s)

| Operation | Downstream | Lag |
|----------|------------|-----|
| Message sent | `message_tracking` | ~500ms |
| Message sent | `message_events` | ~500ms |
| Message sent | `usage_tracking` | ~500ms |
| Webhook received | `domain_events` | ~100ms |

### Batch Processing (Minutes)

| Operation | Downstream | Lag |
|----------|------------|-----|
| Campaign complete | Campaign aggregates | 1-5 min |
| Import complete | `segment_memberships` | 1-5 min |
| Segment materialize | Segment membership count | 1-5 min |

### Eventual Consistency (Events, Minutes to Hours)

| Source Event | Projection | Lag |
|--------------|------------|-----|
| `message.sent` | Contact engagement score | Hours |
| `message.sent` | Campaign analytics rollups | Minutes |
| `contact.imported` | Segment membership refresh | Minutes |

---

## Race Condition Prevention

### Scenario 1: Concurrent Campaign Queue

```
Worker A: POST /campaigns/1/queue (status: draft)
Worker B: POST /campaigns/1/queue (status: draft)
```

**Prevention**: Optimistic lock on status column

```python
result = await session.execute(
    update(Campaign)
    .where(Campaign.id == campaign_id, Campaign.status == 'draft')
    .values(status='queued')
)
if result.rowcount == 0:
    raise HTTPException(409, "Campaign already queued")
```

### Scenario 2: Webhook + Worker Update Same Message

```
Worker A: campaign.send updates campaign_contacts.delivery_status
Worker B: webhook.dispatch updates campaign_contacts.delivery_status
```

**Prevention**: Separate status columns

- `campaign_contacts.delivery_status` — Worker updates
- `message_tracking.current_status` — Webhook updates
- Campaign aggregates query both tables

### Scenario 3: Segment Materialization + Contact Update

```
Worker A: segments.materialize deletes/recreates memberships
Worker B: contact.update modifies contact attributes
```

**Prevention**: Separate tables, no conflict

- `segment_memberships` — Materialization target
- `contacts` — Direct updates
- Segment re-materialization picks up changes atomically

### Scenario 4: Import + Campaign Target Same Contact

```
Worker A: contacts.import_job upserts contact
Worker B: campaign.send reads contacts for audience
```

**Prevention**: Import creates new `campaign_contacts` entries

- Import creates/updates `contacts`
- Campaign audience stored separately in `campaign_contacts`
- Audience snapshot taken at queue time

---

## Indexing Strategy

### Write-Heavy Tables

| Table | Key Indexes | Purpose |
|-------|-------------|---------|
| `contacts` | `(workspace_id, phone)` | Dedupe, lookup |
| `campaign_contacts` | `(campaign_id, idempotency_key)` | Idempotency |
| `message_tracking` | `(provider_message_id)` | Webhook lookup |
| `webhook_ingestions` | `(status, created_at)` | Retry queries |
| `domain_events` | `(workspace_id, event_type, created_at)` | Event queries |

### Read-Heavy Tables

| Table | Key Indexes | Purpose |
|-------|-------------|---------|
| `message_events` | `(campaign_id, status)` | Analytics |
| `contact_activities` | `(contact_id, created_at)` | Activity feed |
| `segment_memberships` | `(segment_id, contact_id)` | Membership lookup |

---

## Connection Pool Management

### Per-Worker Pool Allocation

| Worker Type | Concurrency | Pool Size |
|-------------|-------------|-----------|
| API (uvicorn) | 1-4 | 5-10 connections |
| Campaign Worker | 4 | 8-12 connections |
| Webhook Worker | 20 | 2-4 connections |
| Import Worker | 2 | 4-8 connections |

### Pool Configuration

```env
DATABASE_POOL_SIZE=10           # Base pool
DATABASE_MAX_OVERFLOW=20        # Burst capacity
DATABASE_POOL_TIMEOUT=30       # Wait time
DATABASE_POOL_RECYCLE=1800     # Connection refresh
```

---

## Future Considerations

### Read Replicas

For analytics-heavy workloads:

```
Primary: Writes only
Replica 1: API reads (campaigns, contacts)
Replica 2: Analytics queries
```

### Sharding Strategy

For multi-tenant scale:

```
Shard by workspace_id
→ Each workspace on dedicated shard
→ Cross-workspace queries rare (admin only)
```

### Connection Pooler

Consider PgBouncer for high-concurrency scenarios:

```yaml
# pgbouncer.ini
pool_mode = transaction
max_client_conn = 1000
default_pool_size = 25
```
