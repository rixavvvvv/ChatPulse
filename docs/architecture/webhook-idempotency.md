# Webhook Idempotency Architecture

> Provider-level idempotency keys, dual-layer dedupe, and replay guarantees. Last updated: 2026-05-12.

---

## Problem Statement

Previous implementation used timestamp-based short-window dedupe for webhook processing:

```python
# OLD (UNSAFE): Timestamp-based dedupe
since = datetime.now(tz=UTC) - timedelta(seconds=settings.webhook_dedupe_ttl_seconds)
stmt = select(WebhookIngestion).where(
    WebhookIngestion.source == source,
    WebhookIngestion.dedupe_key == dedupe_key,
    WebhookIngestion.received_at >= since,  # Time window is unreliable
)
```

**Problems with timestamp-based dedupe:**
1. Webhooks may arrive out of order
2. Same event may arrive with different timestamps
3. Replays may have different timestamps than originals
4. Time window boundaries cause edge-case failures

---

## Solution: Provider-Level Idempotency Keys

### Core Principle

Each webhook source provides a stable, unique identifier for each event. Use this identifier as the idempotency key.

| Source | Event ID | Field in Payload |
|--------|----------|-------------------|
| Meta WhatsApp | wamid (delivery/read) | `entry[].changes[].value.statuses[].id` |
| Meta WhatsApp | message ID (incoming) | `entry[].changes[].value.messages[].id` |
| Shopify Orders | order_id | `payload.id` |

### Idempotency Key Schema

```
webhook_idempotency:{source}:{provider_event_id}
```

Examples:
- `webhook_idempotency:meta_whatsapp:wamid_HBAMPLE123`
- `webhook_idempotency:shopify_orders:123456789`

---

## Dual-Layer Idempotency

### Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dual-Layer Idempotency                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Layer 1: Redis (Fast Path)                                      │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Purpose: Immediate dedupe of concurrent requests           │ │
│  │  Mechanism: SETNX (atomic "set if not exists")              │ │
│  │  TTL: 24 hours (configurable)                               │ │
│  │  Keys:                                                      │ │
│  │    - webhook:idempotency:{source}:{id} → processing        │ │
│  │    - webhook:completed:{source}:{id} → ingestion_id        │ │
│  │    - webhook:processing:{source}:{id} → ingestion_id       │ │
│  └────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  Layer 2: PostgreSQL (Authoritative)                            │
│  ┌────────────────────────────────────────────────────────────┐ │
│  │  Purpose: Persist authoritative dedupe across restarts     │ │
│  │  Mechanism: UNIQUE CONSTRAINT on (source, provider_event_id)│ │
│  │  Handles: Redis failures, worker restarts, race conditions   │ │
│  │  Table: webhook_ingestions                                  │ │
│  └────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Why Two Layers?

| Scenario | Redis Handles | PostgreSQL Handles |
|----------|--------------|-------------------|
| Concurrent webhook delivery | ✅ Fast SETNX dedupe | ✅ Unique constraint catch |
| Worker crash mid-processing | ✅ Processing lock | ✅ Status check on restart |
| Redis failure/unavailable | ❌ Unavailable | ✅ DB still works |
| PostgreSQL race condition | ✅ SETNX prevents duplicate | ✅ Unique constraint catch |
| Replay after failure | ✅ Lock release | ✅ Status update |

---

## Idempotency Check Flow

### 1. Webhook Arrival

```
HTTP Request → /webhook/meta or /webhook/order-created
    │
    ▼
Parse payload
    │
    ▼
Extract provider_event_id
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  check_and_acquire()                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  Step 1: Redis Fast Path                                         │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  key = f"webhook:idempotency:{source}:{provider_event_id}"  │ │
│  │  acquired = redis.set(key, "processing", ex=ttl, nx=True)  │ │
│  │                                                               │ │
│  │  if not acquired:                                            │ │
│  │      existing = redis.get(key)                               │ │
│  │      if existing == "completed":                             │ │
│  │          return DUPLICATE (fast path)                        │ │
│  │      else:                                                   │ │
│  │          return IN_FLIGHT (another worker processing)        │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  Step 2: PostgreSQL Authoritative                               │
│  ┌─────────────────────────────────────────────────────────────┐ │
│  │  INSERT INTO webhook_ingestions                              │ │
│  │    (source, provider_event_id, dedupe_key, ...)              │ │
│  │  ON CONFLICT (source, provider_event_id) DO NOTHING         │ │
│  │                                                               │ │
│  │  if IntegrityError:                                          │ │
│  │      return DUPLICATE (unique constraint violation)          │ │
│  │  else:                                                       │ │
│  │      return NEW (ingestion created)                          │ │
│  └─────────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### 2. Dispatch Task Execution

```
Celery Task → process_webhook_ingestion(ingestion_id)
    │
    ▼
Load ingestion from DB
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│              Provider-Level Idempotency Check                    │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  if provider_event_id:                                          │
│      result = await service.check_and_acquire(                  │
│          session=session,                                       │
│          source=row.source,                                      │
│          provider_event_id=row.provider_event_id,                │
│          dedupe_key=row.dedupe_key,                             │
│      )                                                          │
│      if result.is_duplicate and not result.should_process:      │
│          return {"status": "duplicate_skipped", ...}            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
    │
    ▼
Mark as processing in Redis
    │
    ▼
Execute business logic
    │
    ▼
Mark as completed in Redis + PostgreSQL
    │
    ▼
OR on failure:
    │
    ▼
Release Redis lock (allow retry)
    │
    ▼
Mark as failed in PostgreSQL
```

---

## Replay Guarantees

### Replay Flow

```
POST /admin/queues/webhook-ingestions/replay
{
  "ingestion_ids": [1, 2, 3]
}
    │
    ▼
For each ingestion:
    │
    ▼
1. Release Redis lock (allow reprocessing)
   - Delete processing key
   - Delete idempotency key
    │
    ▼
2. Update PostgreSQL
   - Set processing_status = "queued"
   - Increment replay_count
   - Set last_replay_at = now()
   - Clear error_message, completed_at, dispatch_result
    │
    ▼
3. Enqueue new dispatch task
    │
    ▼
4. Idempotency check runs again
   - Same provider_event_id
   - Either new ingestion or already-completed check passes
```

### Replay Idempotency Guarantees

| Property | How Achieved |
|----------|-------------|
| Same replay, same result | Provider event ID is constant across replays |
| No duplicate processing | Redis SETNX prevents concurrent replay execution |
| No duplicate DB records | PostgreSQL unique constraint prevents duplicate insert |
| Lock cleanup | Failed ingestions release their Redis lock on replay |

---

## At-Least-Once vs Exactly-Once

### Delivery Semantics Matrix

| Semantic | Guarantee | Use Case | Implementation |
|----------|-----------|----------|-----------------|
| At-Least-Once | Every message delivered at least once, may have duplicates | Message queuing | Celery with late ACK |
| At-Most-Once | Every message delivered at most once, may be lost | Fire-and-forget notifications | Standard acknowledgment |
| Exactly-Once | Every message delivered exactly once, no duplicates or loss | Critical business operations | Idempotency + deduplication |

### Our Implementation

We provide **effectively exactly-once** semantics:

```
┌─────────────────────────────────────────────────────────────────┐
│                 Exactly-Once Delivery Path                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. Duplicate webhook delivery:                                 │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  Meta resends same wamid                                 │ │
│     │    → Redis SETNX: "already processing"                  │ │
│     │    → PostgreSQL: UNIQUE constraint violation            │ │
│     │    → Return 200 OK, no duplicate ingestion              │ │
│     └─────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  2. Worker crash mid-processing:                                │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  Worker picks up task, starts processing                  │ │
│     │    → task_acks_late = True (message NOT acknowledged)   │ │
│     │    → Worker crashes (OOM, SIGKILL, container restart)   │ │
│     │    → Message NOT removed from Redis broker              │ │
│     │    → Visibility timeout expires (5 min)                 │ │
│     │    → Message returned to queue                          │ │
│     │    → New worker picks up task                           │ │
│     │    → Idempotency check: Redis "processing" key found     │ │
│     │    → Check PostgreSQL status                             │ │
│     │    → Skip if completed, process if failed               │ │
│     └─────────────────────────────────────────────────────────┘ │
│                              │                                  │
│                              ▼                                  │
│  3. Replay after failure:                                        │
│     ┌─────────────────────────────────────────────────────────┐ │
│     │  Ingestion marked as failed                              │ │
│     │    → Admin triggers replay                              │ │
│     │    → Redis lock released                                │ │
│     │    → New task enqueued                                  │ │
│     │    → Idempotency check: new ingestion or completed check │ │
│     │    → Process again                                       │ │
│     └─────────────────────────────────────────────────────────┘ │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### Why "Effectively" Not "Truly" Exactly-Once

True exactly-once delivery is not achievable in distributed systems due to the Two General's Problem. We provide "effectively exactly-once" by:

1. **Preventing duplicates at ingestion**: Redis + PostgreSQL dual-layer dedupe
2. **Preventing duplicates at dispatch**: Status check + Redis lock
3. **Handling non-idempotent operations at business logic layer**:
   - Order confirmations: Track `order_created_sent` flag
   - Inventory updates: Optimistic locking with version numbers
   - Payment processing: Idempotency keys at payment provider level

---

## Redis Key Patterns

| Key Pattern | Purpose | TTL |
|-------------|---------|-----|
| `webhook:idempotency:{source}:{event_id}` | Idempotency lock | 24h |
| `webhook:processing:{source}:{event_id}` | In-progress processing | 24h |
| `webhook:completed:{source}:{event_id}` | Completed ingestion ID | 24h |

### Key Lifecycle

```
1. Ingestion:
   SET webhook:idempotency:meta_whatsapp:wamid123 "processing" EX 86400 NX
        │
        ▼
2. Dispatch starts:
   SET webhook:processing:meta_whatsapp:wamid123 "123" EX 86400

3. Dispatch completes:
   SET webhook:completed:meta_whatsapp:wamid123 "123" EX 86400
   DEL webhook:processing:meta_whatsapp:wamid123
   SET webhook:idempotency:meta_whatsapp:wamid123 "completed:123" EX 86400

4. Replay (if failed):
   DEL webhook:idempotency:meta_whatsapp:wamid123
   DEL webhook:completed:meta_whatsapp:wamid123
   DEL webhook:processing:meta_whatsapp:wamid123
   (New ingestion with same provider_event_id will re-create keys)
```

---

## Configuration

### Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `WEBHOOK_DEDUPE_TTL_SECONDS` | 86400 | TTL for idempotency keys (24 hours) |
| `QUEUE_IDEMPOTENCY_TTL_SECONDS` | 86400 | TTL for task idempotency keys |

### PostgreSQL Constraints

```sql
-- Primary idempotency constraint
ALTER TABLE webhook_ingestions
ADD CONSTRAINT uq_webhook_source_provider_event_id
UNIQUE (source, provider_event_id);

-- Indexes for fast lookups
CREATE INDEX ix_webhook_ingestions_source_status
ON webhook_ingestions (source, processing_status);

CREATE INDEX ix_webhook_ingestions_status_replay
ON webhook_ingestions (processing_status, replay_count);
```

---

## Monitoring

### Key Metrics

| Metric | Type | Description |
|--------|------|-------------|
| `webhook.idempotency.duplicate` | Counter | Duplicates detected (labels: source, reason) |
| `webhook.idempotency.new` | Counter | New ingestions created |
| `webhook.idempotency.redis_hit` | Counter | Redis cache hits |
| `webhook.idempotency.pg_fallback` | Counter | PostgreSQL fallback hits |

### Alert Thresholds

| Metric | Alert When |
|--------|------------|
| `webhook.idempotency.duplicate` | > 10% of total webhooks |
| `webhook.dispatch.errors` | > 5% failure rate |
| `webhook.dispatch.latency` | > 95th percentile > 1s |

---

## Error Handling

### Redis Unavailable

If Redis is unavailable, PostgreSQL remains the authoritative source:
1. Idempotency check falls back to PostgreSQL only
2. SETNX is skipped
3. UNIQUE constraint still prevents duplicates

### PostgreSQL IntegrityError

If UNIQUE constraint is violated:
1. This is expected for duplicate webhooks
2. Return success (200 OK) to provider
3. Log duplicate detection for metrics

### Lock Timeout

If processing exceeds TTL:
1. Redis key expires
2. Next request creates new ingestion
3. Use `last_replay_at` to detect stuck ingestions

---

## Testing

### Idempotency Tests

```python
async def test_duplicate_meta_webhook():
    """Simulate Meta sending same wamid twice."""
    payload = {"entry": [{"changes": [{"value": {"statuses": [{"id": "wamid123"}]}}]}]}
    raw_body = json.dumps(payload).encode()

    # First request - should create ingestion
    result1 = await accept_meta_whatsapp_webhook(session, raw_body=raw_body, payload=payload, ...)
    assert result1["deduplicated"] is False

    # Second request - should be deduplicated
    result2 = await accept_meta_whatsapp_webhook(session, raw_body=raw_body, payload=payload, ...)
    assert result2["deduplicated"] is True
    assert result1["ingestion_id"] == result2["ingestion_id"]

async def test_replay_creates_new_task():
    """Simulate replay after failure."""
    # Create failed ingestion
    ingestion = await create_webhook_ingestion(..., provider_event_id="order123")
    ingestion.processing_status = "failed"
    await session.commit()

    # Replay
    results = await replay_webhook_ingestions(session, ingestion_ids=[ingestion.id])

    # Should have new task and incremented replay_count
    assert results[0]["status"] == "requeued"
    assert results[0]["replay_count"] == 1
```

---

## References

- [CELERY_CRASH_RECOVERY.md](./CELERY_CRASH_RECOVERY.md) - Task crash recovery lifecycle
- [queue-topology.md](./queue-topology.md) - Queue architecture and message flow
- [worker-scaling.md](./worker-scaling.md) - Worker configuration and scaling
- [app/services/webhook_idempotency_service.py](../../app/services/webhook_idempotency_service.py) - Implementation
- [app/models/webhook_ingestion.py](../../app/models/webhook_ingestion.py) - Model with unique constraint