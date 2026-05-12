# Production-Readiness Audit Report

> ChatPulse Architecture Analysis | Date: 2026-05-12

---

## Executive Summary

**System Status**: Pre-production with significant architectural gaps

| Category | Status | Risk Level |
|----------|--------|------------|
| Queue Architecture | Partial | Medium |
| Retry Logic | Inconsistent | High |
| Webhook Idempotency | Weak | Critical |
| Service Boundaries | Blurred | Medium |
| Database Schema Quality | Adequate | Low |
| Query Performance | At-risk | High |
| Transaction Safety | Fragile | High |
| Redis Usage Patterns | Adequate | Medium |
| N+1 Query Risks | Present | Medium |
| Soft Delete Consistency | Partial | Medium |
| Logging Consistency | Inconsistent | Medium |
| WebSocket Readiness | None | High |
| Worker Failure Handling | Absent | Critical |

---

## 1. Queue Architecture Audit

### Findings

**Weaknesses**:
- `app/queue/registry.py:33-40`: Task routing only configures webhook tasks; campaign.send and bulk.send use default queue
- `app/queue/registry.py:11-17`: QueueNames defines 5 queues but only 1 (`webhooks`) is actually configured for routing
- `app/queue/celery_app.py:15-25`: Missing `worker_prefetch_multiplier`, `task_acks_late`, `task_reject_on_worker_lost`

**Dangerous Technical Debt**:
```python
# app/queue/celery_app.py - Missing critical settings
celery_app.conf.update(
    task_default_queue=settings.celery_default_queue,
    task_routes=celery_task_routes(),
    task_create_missing_queues=True,
    # MISSING: task_acks_late=True  <- Critical for reliability
    # MISSING: worker_prefetch_multiplier=1  <- Critical for fair dispatch
    # MISSING: task_reject_on_worker_lost=True
)
```

**Scalability Risks**:
- All tasks default to `bulk-messages` queue — no isolation between campaigns, imports, segments
- Missing priority queues for time-sensitive operations

**Recommendations**:
1. Add explicit routing for all task types
2. Configure `task_acks_late=True` to prevent task loss on worker crash
3. Set `worker_prefetch_multiplier=1` for fair dispatch across long-running campaigns

---

## 2. Retry Logic Audit

### Findings

**Inconsistent Retry Behavior**:

| Location | Retry Implementation | Issues |
|----------|---------------------|--------|
| `app/queue/tasks.py:142-147` | Campaign retry with backoff | Duplicated in message_dispatch_service |
| `app/services/message_dispatch_service.py:37-38,60-104` | Dispatch retry logic | **Duplicates** tasks.py logic |
| `app/queue/tasks.py:326-367` | Billing check inside retry loop | Runs on every retry attempt |

**Dangerous Technical Debt**:
```python
# app/services/message_dispatch_service.py - RETRY LOGIC DUPLICATED
def _retry_delay_seconds(attempt: int, base_delay: int) -> int:
    return base_delay * (2 ** max(0, attempt - 1))  # DUPLICATE of tasks.py:142

# app/queue/tasks.py - SAME LOGIC
def _retry_delay_seconds(attempt: int, suggested_delay: int | None = None) -> int:
    exponential = settings.queue_retry_base_delay_seconds * (2 ** max(0, attempt - 1))
```

**Unsafe Retry Flow**:
```python
# app/queue/tasks.py:326-330 - BILLING CHECK ON EVERY RETRY
try:
    await ensure_workspace_can_send(  # Called on EACH retry attempt
        session=session,
        workspace_id=workspace_id,
        requested_count=1,
    )
```
**Issue**: Billing check runs on every retry, potentially exhausting quota mid-campaign

**Race Condition in Retry**:
```python
# app/queue/tasks.py:320-367 - Non-atomic retry loop
while attempt < settings.queue_retry_max_attempts and not delivered:
    attempt += 1
    # ... send attempt
    # If billing check passes but quota exhausts mid-send, wasted retry
```

**Recommendations**:
1. Extract retry logic to shared `app/retry/` module
2. Pre-check quota before entering retry loop
3. Add circuit breaker for failed sends

---

## 3. Webhook Idempotency Audit

### Findings

**Critical Gaps**:
- `app/routes/webhook_meta.py:54-102`: Rate limiting happens AFTER signature verification — attackers can exhaust compute
- No idempotency key extraction from Meta webhook `id` field before processing
- `app/services/webhook_service.py:231-233`: Timestamp check is present but not using idempotency key

**Missing Deduplication**:
```python
# app/services/webhook_service.py - NO DEDUP BY MESSAGE ID
if tracking.last_webhook_at and webhook_time and webhook_time < tracking.last_webhook_at:
    result.ignored += 1
    continue
# ISSUE: Only checks timestamp ordering, not idempotency by message ID
```

**Event Replay Risks**:
```python
# app/services/webhook_dispatcher_service.py:46-47
if row.processing_status == WebhookIngestionStatus.completed.value:
    return dict(row.dispatch_result or {"status": "already_completed"})
# ISSUE: Returns "success" for already-completed — but doesn't check if result was actually successful
```

**Dangerous Replay Pattern**:
```python
# webhook_ingestion_service.py - Replay can re-trigger side effects
async def replay_webhook_ingestions(session, ingestion_ids):
    for row in rows:
        row.processing_status = WebhookIngestionStatus.pending.value
        row.retry_count += 1
        row.replayed_at = datetime.now(tz=UTC)
        # ISSUE: Replay doesn't check if original process succeeded or failed
```

**Recommendations**:
1. Implement proper idempotency key (Meta's `message.id`) before processing
2. Add deduplication check in `webhook_ingestions` table by `event_id + source`
3. Track `replay_result` separately from original result

---

## 4. Service Boundaries Audit

### Findings

**Blurred Boundaries**:

| Service | Boundary Violations |
|---------|---------------------|
| `CampaignService` | Modifies `campaign_contacts.delivery_status` from webhook context |
| `WebhookService` | Updates `campaign_contacts` records — crosses to Messaging boundary |
| `BulkService` | Duplicates tracking logic from `MessageDispatchService` |
| `MessageDispatchService` | Does NOT call `BillingService` — billing is checked in `queue/tasks.py` |

**Cross-Boundary Writes**:
```python
# app/services/webhook_service.py:258-261 - CROSS-BOUNDARY WRITE
if campaign_contact and target_status == MessageTrackingStatus.failed:
    campaign_contact.delivery_status = CampaignContactDeliveryStatus.failed
    campaign_contact.failure_classification = CampaignFailureClassification.api_error
    campaign_contact.last_error = tracking.last_error
# ISSUE: WebhookService (Event Infrastructure) modifies Campaign domain entities
```

**Duplicated Business Logic**:

| Logic | Location A | Location B |
|-------|------------|------------|
| Error classification | `tasks.py:126-139` | `message_dispatch_service.py:27-34` |
| Retry delay calculation | `tasks.py:142-147` | `message_dispatch_service.py:37-38` |
| Template parameter building | `tasks.py:293-302` | `bulk_service.py:138-147` |

**Missing Abstraction**:
```python
# No abstraction for "Send Service" - logic scattered across:
# - whatsapp_service.py (low-level API)
# - message_dispatch_service.py (tracking + retry)
# - queue/tasks.py (orchestration)
# - bulk_service.py (batch send)
```

**Recommendations**:
1. Move `campaign_contacts` updates out of `WebhookService` — use event-driven updates
2. Create single `SendService` abstraction
3. Extract shared retry/error logic to `app/retry/` module

---

## 5. Database Schema Quality Audit

### Findings

**Good Practices**:
- Unique constraints properly defined
- Foreign keys with `ondelete="CASCADE"` for contact entities
- JSONB for flexible payload storage
- Soft delete via `deleted_at` for notes

**Missing Indexes**:

| Table | Missing Index | Query Pattern |
|-------|---------------|--------------|
| `campaign_contacts` | `(workspace_id, campaign_id, delivery_status)` | Progress queries, status filtering |
| `contact_activities` | `(contact_id, created_at)` | Activity feed |
| `domain_events` | `(workspace_id, event_type, created_at)` | Event queries |
| `segment_memberships` | `(segment_id)` for membership lookup | Materialization queries |
| `contacts` | `(workspace_id, tags)` | Tag-based queries |

**N+1 Query Risks**:

```python
# app/services/webhook_service.py:251-257 - N+1 QUERY
if tracking.campaign_contact_id is not None:
    contact_stmt = select(CampaignContact).where(  # 1 query per webhook
        CampaignContact.id == tracking.campaign_contact_id,
        CampaignContact.workspace_id == tracking.workspace_id,
    )
    campaign_contact = (await session.execute(contact_stmt)).scalar_one_or_none()
```

**Batch Insert Issues**:
```python
# app/services/segment_service.py:80-84 - SINGLE INSERT PATTERN
rows = [
    {"workspace_id": workspace_id, "segment_id": segment.id, "contact_id": cid}
    for cid in contact_ids
]
await session.execute(insert(SegmentMembership), rows)
# ISSUE: Works for small segments, will fail/memory-exhaust for large segments
```

**Recommendations**:
1. Add composite indexes for common query patterns
2. Batch process segment membership inserts (chunk into 1000-record batches)
3. Pre-fetch campaign_contacts in webhook processing with JOIN

---

## 6. Query Performance Risks

### Findings

**Expensive Aggregation Queries**:

```python
# app/services/campaign_service.py:47-70 - 5 SEPARATE QUERIES
total_stmt = select(func.count(CampaignContact.id)).where(...)
sent_stmt = select(func.count(CampaignContact.id)).where(...)
failed_stmt = select(func.count(CampaignContact.id)).where(...)
skipped_stmt = select(func.count(CampaignContact.id)).where(...)
# ISSUE: 4-5 queries instead of single query with aggregation

# app/services/webhook_service.py:292-297 - N+1 REFRESH
for workspace_id, campaign_id in impacted_campaigns:
    await _refresh_campaign_aggregates(...)  # Multiple queries per campaign
# ISSUE: Called in loop — could batch into single query
```

**No Pagination**:
```python
# app/services/campaign_service.py:223
audience = list(audience_result.scalars().all())
# ISSUE: Loads ALL campaign contacts into memory at once
# For 100K contact campaign: potential OOM
```

**Full Table Scans Risk**:
```python
# app/services/segment_service.py:69-73 - NO LIMIT
contacts_stmt = select(Contact.id).where(
    Contact.workspace_id == workspace_id,
    compiled.where_clause,
)
contact_ids = list((await session.execute(contacts_stmt)).scalars().all())
# ISSUE: No pagination — will fail for large workspaces
```

**Recommendations**:
1. Combine multiple COUNT queries into single aggregated query
2. Add cursor-based pagination for audience loading
3. Chunk large segment materialization into batches

---

## 7. Transaction Safety Audit

### Findings

**Unsafe Transaction Boundary**:

```python
# app/services/message_dispatch_service.py:92
await session.commit()
return DispatchResult(...)  # Commit AFTER return statement in try block
# ISSUE: If session.commit() fails after return, error swallowed
```

**Non-Atomic Campaign Updates**:
```python
# app/queue/tasks.py:376-378 - NON-ATOMIC AGGREGATE UPDATE
campaign.success_count = success_count
campaign.failed_count = failed_count
await session.commit()  # Only commits counts, not individual contacts
# ISSUE: If worker crashes after commit but before final status, inconsistent state
```

**Missing Transaction Isolation**:
```python
# app/services/webhook_service.py - No explicit transaction isolation
# Concurrent webhooks for same message could race:
# Thread A: SELECT tracking WHERE wamid = X
# Thread B: SELECT tracking WHERE wamid = X
# Thread A: UPDATE status = 'delivered'
# Thread B: UPDATE status = 'read'
# Result: 'read' overwrites 'delivered' (not always wrong, but race exists)
```

**Engine Lifecycle Issues**:
```python
# app/queue/tasks.py:52 - asyncio.run() in task wrapper
def _run_with_engine_reset(coro):
    async def _runner():
        try:
            return await coro
        finally:
            await _dispose_engine()
    return asyncio.run(_runner())  # ISSUE: Creates new event loop per task
# For Celery with gevent/eventlet: This pattern will FAIL
```

**Recommendations**:
1. Refactor task wrapper to use Celery's built-in async task handling
2. Use explicit transaction boundaries with `session.begin()`
3. Add pessimistic locking for campaign status transitions

---

## 8. Redis Usage Patterns Audit

### Findings

**Good Practices**:
- Sliding window rate limiting implemented correctly
- Pipeline usage for atomic operations
- Proper key namespacing

**Issues**:

**Non-Atomic Rate Limit Check**:
```python
# app/queue/rate_limit.py:35-50 - RACE CONDITION
async with redis.pipeline(transaction=True) as pipe:
    pipe.zremrangebyscore(key, 0, now_ms - window_ms)
    pipe.zcard(key)
    cleaned = await pipe.execute()

current_count = int(cleaned[1])  # <- Read after pipeline
if current_count >= max_events:
    raise WebhookIngestRateLimitExceeded(...)
# ISSUE: Between pipeline execute and check, another request could increment
# FIX: Use Lua script for atomicity
```

**Missing Redis Error Handling**:
```python
# app/queue/tasks.py:96-97 - NO ERROR HANDLING
async def _already_sent(redis: Redis, idempotency_key: str) -> bool:
    return bool(await redis.exists(_sent_key(idempotency_key)))
# ISSUE: If Redis is down, returns False -> potential duplicate sends
```

**Connection Leak Risk**:
```python
# app/routes/webhook_meta.py:61-72 - Redis connection not in context manager
redis = Redis.from_url(settings.redis_url, decode_responses=True)
try:
    # ...
finally:
    await redis.aclose()
# ISSUE: If exception during rate limit check, connection may leak
```

**Key Expiration Race**:
```python
# app/queue/tasks.py:81-89 - _mark_sent RACE CONDITION
async with redis.pipeline(transaction=True) as pipe:
    pipe.set(_sent_key(...), "1", ex=...)
    pipe.delete(_inflight_key(...))  # <- Delete inflight AFTER setting sent
    await pipe.execute()
# ISSUE: Small window where inflight key deleted but sent key not yet set
# If task crashes in this window, re-execution allowed
```

**Recommendations**:
1. Implement Lua scripts for atomic rate limiting
2. Add Redis connection error handling with fallback (deny-safe)
3. Use `WATCH/MULTI/EXEC` or Lua for atomic key operations

---

## 9. Soft Delete Consistency Audit

### Findings

**Inconsistent Soft Delete Patterns**:

| Entity | Soft Delete? | Implementation |
|--------|--------------|----------------|
| `ContactNote` | ✅ Yes | `deleted_at` timestamp |
| `Campaign` | ❌ No | Only status field |
| `Segment` | ❌ No | Only `status` field |
| `Tag` | ❌ No | No deletion mechanism |

**Missing Soft Delete for Critical Entities**:
```python
# app/services/contact_note_service.py - Proper soft delete
async def soft_delete_note(session, contact_id, note_id):
    note.deleted_at = datetime.now(tz=UTC)  # Soft delete
    await session.commit()

# app/services/campaign_service.py - Hard delete possible
# No soft delete pattern — campaigns can only be "archived" via status
```

**Orphaned Related Data**:
```python
# Campaign deletion scenario:
# DELETE campaign WHERE id = X
# -> campaign_contacts orphaned (no CASCADE to contacts)
# -> segment_memberships not affected
# -> message_events not affected
# ISSUE: Analytics may reference deleted campaigns
```

**Recommendations**:
1. Add soft delete pattern for Campaigns, Segments
2. Implement cascade soft delete for related entities
3. Add `WHERE deleted_at IS NULL` filter to all active entity queries

---

## 10. Logging Consistency Audit

### Findings

**Inconsistent Log Levels**:

| Location | Log Level | Issue |
|----------|-----------|-------|
| `tasks.py:177-181` | INFO | No trace_id |
| `tasks.py:414-418` | INFO | No trace_id |
| `whatsapp_service.py:224-229` | WARNING | No trace_id |
| `webhook_dispatcher_service.py:82` | exception | Missing context |

**Missing Structured Logging**:
```python
# Current pattern - unstructured
logger.info(
    "Campaign queue task started workspace_id=%s campaign_id=%s",
    workspace_id,
    campaign_id,
)
# ISSUE: Not JSON, not machine-parseable, no trace_id

# Missing from ALL log statements:
# - trace_id
# - workspace_id (in most places)
# - user_id where applicable
# - request_id for HTTP endpoints
```

**No Error Context**:
```python
# app/services/message_dispatch_service.py:99
except Exception as exc:  # pragma: no cover
    last_error = str(exc)  # <- Only string, no context
# ISSUE: No stack trace in logs, no request context
```

**Recommendations**:
1. Implement structured JSON logging
2. Add trace_id to all async tasks
3. Standardize log fields: `trace_id`, `workspace_id`, `campaign_id`

---

## 11. WebSocket Architecture Readiness

### Findings

**Current State**: No WebSocket implementation

**Missing Infrastructure**:
- No WebSocket gateway
- No pub/sub mechanism for real-time updates
- No room/topic architecture
- No SSE fallback

**Architecture Gap**:
```
# What's needed but missing:
1. WebSocket connection manager
2. Room management (workspace, campaign, contact)
3. Event broadcasting to connected clients
4. Reconnection with backoff
5. Authentication over WebSocket
```

**Recommendations**:
1. Plan WebSocket gateway for v2
2. Use Redis pub/sub for cross-instance messaging
3. Implement SSE for simpler clients

---

## 12. Worker Failure Handling Audit

### Findings

**Critical Missing Features**:

```python
# app/worker.py - Empty worker entry point
from app.queue.celery_app import celery_app
__all__ = ["celery_app"]
# ISSUE: No signal handlers for graceful shutdown
# ISSUE: No on_failure callback
# ISSUE: No on_retry callback
# ISSUE: No dead letter queue handler
```

**No Task Failure Callbacks**:
```python
# Missing: @celery_app.task(...)
# - on_failure: Send alert, update status
# - on_retry: Log retry attempt
# - after_return: Cleanup
```

**No Visibility into Worker State**:
- No Prometheus metrics export
- No health check endpoint for workers
- No task result backend inspection

**Recommendations**:
1. Add Celery signal handlers for task lifecycle events
2. Export Prometheus metrics from workers
3. Implement dead letter queue alerting

---

## Critical Issues Summary

### P0 — Production Blockers

| Issue | Location | Impact |
|-------|----------|--------|
| No `task_acks_late` configured | `celery_app.py` | Task loss on worker crash |
| Missing idempotency by message ID | `webhook_service.py` | Duplicate message processing |
| Non-atomic rate limiting | `rate_limit.py` | Rate limit bypass |
| Worker crash = campaign stuck | `tasks.py` | No recovery mechanism |

### P1 — High Priority

| Issue | Location | Impact |
|-------|----------|--------|
| Duplicate retry logic | `tasks.py` + `message_dispatch_service.py` | Maintenance burden |
| Cross-boundary writes | `webhook_service.py` | Integrity issues |
| N+1 queries in webhooks | `webhook_service.py:251-257` | Performance |
| No pagination for audiences | `campaign_service.py` | Memory exhaustion |
| Missing Redis error handling | `tasks.py:96-97` | Unbounded retries |

### P2 — Medium Priority

| Issue | Location | Impact |
|-------|----------|--------|
| Inconsistent logging | All services | Debug difficulty |
| No soft delete for campaigns | `campaign_service.py` | Data integrity |
| Missing composite indexes | Multiple tables | Query performance |
| No WebSocket infrastructure | N/A | Future roadmap gap |

---

## Production Hardening Checklist

### Must Complete Before Production

#### Queue & Worker
- [ ] Configure `task_acks_late=True`
- [ ] Set `worker_prefetch_multiplier=1`
- [ ] Add `task_reject_on_worker_lost=True`
- [ ] Implement worker signal handlers
- [ ] Add dead letter queue monitoring

#### Webhook Processing
- [ ] Implement idempotency by Meta message ID
- [ ] Add Lua script for atomic rate limiting
- [ ] Fix signature verification ordering (verify AFTER rate limit)
- [ ] Add replay safety checks

#### Transaction Safety
- [ ] Refactor `asyncio.run()` pattern in Celery tasks
- [ ] Add pessimistic locking for campaign status transitions
- [ ] Fix non-atomic campaign aggregate updates
- [ ] Add transaction isolation levels where needed

#### Performance
- [ ] Add composite indexes for common query patterns
- [ ] Implement cursor pagination for audiences
- [ ] Batch segment membership inserts
- [ ] Combine multiple COUNT queries into single

#### Observability
- [ ] Implement structured JSON logging
- [ ] Add trace_id to all async tasks
- [ ] Add Prometheus metrics export
- [ ] Configure log aggregation

#### Data Integrity
- [ ] Add soft delete for campaigns
- [ ] Implement cascade soft delete
- [ ] Add `WHERE deleted_at IS NULL` to queries
- [ ] Fix cross-boundary writes

---

## Scaling Concerns

### Near-Term (100K contacts, 10 campaigns/day)

**Immediate Actions**:
1. Add database indexes for query patterns
2. Implement cursor pagination for large audiences
3. Separate worker queues for different task types

### Mid-Term (1M contacts, 100 campaigns/day)

**Required Changes**:
1. Read replicas for analytics queries
2. Redis cluster for high availability
3. Batch processing for segment materialization
4. Campaign worker auto-scaling

### Long-Term (10M contacts, 1000 campaigns/day)

**Architecture Changes**:
1. Database sharding by workspace_id
2. Kafka for event streaming
3. Separate microservices for bounded contexts
4. CDN for webhook ingress

---

## Recommended Refactoring Priority

### Phase 1: Reliability (Week 1-2)
1. Fix Celery configuration (`task_acks_late`, `worker_prefetch_multiplier`)
2. Implement webhook idempotency
3. Add Lua script for atomic rate limiting
4. Fix transaction boundaries

### Phase 2: Observability (Week 3-4)
1. Structured JSON logging
2. Prometheus metrics
3. Trace ID propagation
4. Alert definitions

### Phase 3: Performance (Week 5-6)
1. Database indexes
2. Cursor pagination
3. Batch processing
4. N+1 query fixes

### Phase 4: Architecture (Week 7-8)
1. Service boundary refactoring
2. Soft delete implementation
3. WebSocket planning
4. Documentation updates
