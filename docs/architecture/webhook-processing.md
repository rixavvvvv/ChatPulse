# Webhook Processing

> Ingestion, verification, dispatch, and replay with provider-level idempotency. Last updated: 2026-05-12.

---

## Overview

The platform uses centralized webhook processing with replay capabilities. All incoming webhooks are stored raw before processing, enabling deduplication, retry, and replay. Provider-level idempotency ensures each event is processed exactly once.

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│   Ingest   │────▶│   Dedup     │────▶│   Store     │
│  (HTTP)    │     │  (Redis+PG) │     │   (Raw)     │
└─────────────┘     └─────────────┘     └─────────────┘
                                              │
                                              ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  Downstream │◀────│  Dispatcher │◀────│   Queue    │
│  Processing │     │  (Worker)  │     │  (Task)    │
└─────────────┘     └─────────────┘     └─────────────┘
```

---

## Provider-Level Idempotency

### The Problem with Timestamp-Based Deduplication

Previous implementation used timestamp-based short-window dedupe (`find_recent_duplicate_ingestion`). This is unsafe because:
- Webhooks may arrive out of order
- Same event may arrive with different timestamps
- Replays may have different timestamps than originals

### The Solution: Provider Event IDs

Each webhook source provides a stable event identifier:

| Source | Event ID | Field in Payload |
|--------|----------|-------------------|
| Meta WhatsApp | wamid | `entry[].changes[].value.statuses[].id` (delivery/read) |
| Meta WhatsApp | message ID | `entry[].changes[].value.messages[].id` (incoming) |
| Shopify Orders | order_id | `payload.id` |

### Dual-Layer Idempotency

```
Layer 1 - Redis (Fast Path):
┌────────────────────────────────────────────────────────┐
│  SETNX webhook:idempotency:{source}:{provider_event_id}│
│  Returns immediately if another worker is processing   │
│  TTL: 24 hours                                         │
└────────────────────────────────────────────────────────┘

Layer 2 - PostgreSQL (Authoritative):
┌────────────────────────────────────────────────────────┐
│  UNIQUE CONSTRAINT (source, provider_event_id)        │
│  Handles race conditions Redis can't catch             │
│  Persists across worker restarts                       │
└────────────────────────────────────────────────────────┘
```

### Idempotency Flow

```
1. Webhook arrives at /webhook/meta or /webhook/order-created
        │
        ▼
2. Extract provider_event_id from payload
   - Meta: Extract wamid from statuses[].id or messages[].id
   - Shopify: Extract order_id from payload.id
        │
        ▼
3. Redis SETNX attempt (atomic)
   - Key: webhook:idempotency:{source}:{provider_event_id}
   - If acquired: proceed to step 4
   - If not acquired: duplicate → return 200 OK
        │
        ▼
4. PostgreSQL INSERT attempt
   - UNIQUE CONSTRAINT on (source, provider_event_id)
   - If inserted: new ingestion created
   - If violated: duplicate → return 200 OK
        │
        ▼
5. Enqueue dispatch task (Celery)
   - Task picks up ingestion_id
   - Checks ingestion status before processing
   - Updates Redis/PG on completion/failure
```

---

## Webhook Sources

### Meta WhatsApp

| Event Type | Trigger | Provider Event ID Source |
|------------|---------|------------------------|
| `message_deliveries` | Delivery receipts | `entry[].changes[].value.statuses[].id` (wamid) |
| `message_reads` | Read receipts | `entry[].changes[].value.statuses[].id` (wamid) |
| `messages` | Incoming messages | `entry[].changes[].value.messages[].id` |

### Shopify Orders

| Event Type | Trigger | Provider Event ID Source |
|------------|---------|------------------------|
| `orders/create` | New order created | `payload.id` (order_id) |
| `orders/updated` | Order status changed | `payload.id` (order_id) |

---

## Processing Flow

### 1. Ingestion (HTTP Handler)

```
POST /webhook/meta
    or
POST /webhook/order-created
    │
    ▼
Extract provider_event_id from payload
    │
    ▼
Redis SETNX check (fast path)
    │
    ▼
PostgreSQL INSERT with UNIQUE CONSTRAINT
    │
    ▼
Store raw in webhook_ingestions
    │
    ▼
Enqueue task
    │
    ▼
Return 200 (fast acknowledgment)
```

### 2. Verification

#### Meta Webhook

```python
# Challenge verification
if mode == "subscribe" and challenge:
    return PlainTextResponse(challenge)

# Signature verification (if META_APP_SECRET set)
signature = request.headers.get("X-Hub-Signature-256")
expected = "sha256=" + hmac.new(app_secret, payload, "sha256").hexdigest()
if not hmac.compare_digest(signature, expected):
    raise HTTPException(403)
```

#### Shopify Webhook

```python
# HMAC verification
secret = get_shopify_webhook_secret(store_identifier)
signature = request.headers.get("X-Shopify-Hmac-SHA256")
expected = base64.b64encode(
    hmac.new(secret.encode(), payload, "sha256").digest()
)
if not hmac.compare_digest(signature, expected):
    raise HTTPException(403)
```

### 3. Storage

`webhook_ingestions` table:

```python
class WebhookIngestion(Base):
    __tablename__ = "webhook_ingestions"
    __table_args__ = (
        # PRIMARY IDEMPOTENCY: unique per provider event
        UniqueConstraint(
            "source",
            "provider_event_id",
            name="uq_webhook_source_provider_event_id",
        ),
    )

    id: Mapped[int]
    source: Mapped[str]                    # meta_whatsapp, shopify_orders
    provider_event_id: Mapped[str]        # Provider's event ID (wamid, order_id)
    dedupe_key: Mapped[str]                # SHA256 of payload for short-window dedupe

    # Payload storage
    payload_json: Mapped[dict | list]     # JSONB
    raw_body: Mapped[bytes | None]        # For Shopify HMAC verification

    # Processing state
    processing_status: Mapped[str]        # received, verified, queued, processing, completed, failed, dead

    # Replay tracking
    replay_count: Mapped[int]             # Number of replay attempts
    last_replay_at: Mapped[datetime | None]
```

### 4. Dispatch (Worker)

```
webhook.dispatch task (acks_late=True)
    │
    ▼
Check Redis completed cache
    │
    ▼
Provider-level idempotency check
    │
    ▼
Update status: processing
    │
    ▼
Mark Redis processing lock
    │
    ▼
Route to appropriate handler:
  - Meta: parse_delivery_status / parse_incoming_message
  - Shopify: parse_order_created
    │
    ▼
Generate domain events
    │
    ▼
Mark status: completed
    │
    ▼
Mark Redis completed
    │
    ▼
OR on failure:
    │
    ▼
Release Redis lock (allow retry)
    │
    ▼
Mark status: failed
    │
    ▼
Store in queue_dead_letters
```

### 5. Domain Events

```python
# After processing
await insert_domain_events_for_ingestion(
    session=session,
    webhook_ingestion_id=ingestion_id,
    events=[
        ("meta.webhook.batch", None, {...}, f"batch:{ingestion_id}"),
        # Provider-specific events from processing
    ]
)
```

---

## Idempotency Service API

### WebhookIdempotencyService

```python
class WebhookIdempotencyService:
    """Dual-layer idempotency service for webhook processing."""

    async def check_and_acquire(
        self,
        session: AsyncSession,
        source: str,
        provider_event_id: str,
        dedupe_key: str,
    ) -> IdempotencyResult:
        """
        Check idempotency and acquire lock if not duplicate.

        Returns IdempotencyResult with:
        - is_duplicate: True if already processed
        - existing_ingestion_id: ID of existing ingestion (if duplicate)
        - new_ingestion_id: ID of new ingestion (if new)
        - should_process: True if should proceed with processing
        - reason: Human-readable reason
        """

    async def mark_processing(
        self,
        source: str,
        provider_event_id: str,
        ingestion_id: int,
    ) -> None:
        """Mark webhook as actively processing in Redis."""

    async def mark_completed(
        self,
        source: str,
        provider_event_id: str,
        ingestion_id: int,
    ) -> None:
        """Mark webhook as completed in Redis."""

    async def release_lock(
        self,
        source: str,
        provider_event_id: str,
    ) -> None:
        """Release idempotency lock for retry scenarios."""
```

### IdempotencyResult

```python
@dataclass(frozen=True)
class IdempotencyResult:
    is_duplicate: bool
    existing_ingestion_id: int | None
    new_ingestion_id: int | None
    should_process: bool
    reason: str
```

---

## Replay System

### Replay-Safe Processing

Each replay increments `replay_count` and sets `last_replay_at`. Provider-level idempotency prevents duplicate downstream effects even when webhooks are replayed multiple times.

### Replay Flow

```
POST /admin/queues/webhook-ingestions/replay
{
  "ingestion_ids": [1, 2, 3]
}
    │
    ▼
For each ingestion:
  1. Release Redis lock (allow reprocessing)
  2. Update status: queued
  3. Increment replay_count
  4. Set last_replay_at timestamp
  5. Clear error_message, completed_at, dispatch_result
  6. Enqueue new task
    │
    ▼
Returns: [{ ingestion_id, status, celery_task_id, replay_count }]
```

### Replay Idempotency

The provider-level idempotency service ensures:
1. **Same replay, same result**: Provider event ID is constant across replays
2. **No duplicate processing**: Redis SETNX prevents concurrent replay execution
3. **Authoritative dedupe**: PostgreSQL unique constraint prevents duplicate DB records
4. **Lock release**: Failed ingestions release their Redis lock for replay

---

## At-Least-Once vs Exactly-Once

### Delivery Semantics

| Delivery Type | Guarantee | Implementation |
|---------------|----------|----------------|
| At-Least-Once | Every webhook delivered at least once, may be duplicated | Celery with late ACK |
| Exactly-Once | Every webhook delivered exactly once, no duplicates | Provider-level idempotency + dispatch dedupe |

### Why "Effectively" Exactly-Once

True exactly-once delivery is not achievable for distributed systems. This implementation provides "effectively exactly-once" semantics:

1. **Duplicate webhook delivery**: Skipped at ingestion (Redis SETNX + PG unique constraint)
2. **Worker crash mid-processing**: Skipped at dispatch (status check + Redis lock)
3. **Replay after failure**: Idempotency key re-checked before execution

### Non-Idempotent Operations

Some business operations are inherently non-idempotent (e.g., sending email on order creation). These are handled at the business logic layer:
- Order confirmations: Track `order_created_sent` flag
- Inventory updates: Use optimistic locking with version numbers
- Financial transactions: Idempotency keys at payment provider level

---

## Rate Limiting

### Per-IP Sliding Window

Configurable via `WEBHOOK_INGEST_RATE_LIMIT_PER_IP_PER_MINUTE` (0 to disable):

```python
async def check_webhook_rate_limit(client_ip: str) -> None:
    key = f"webhook:rate_limit:{client_ip}"
    # Sliding window: remove old, count current, enforce limit
```

---

## Crash Recovery

### Worker Crash During Webhook Processing

```
Worker picks up task
    │
    ▼
task_acks_late = True (message NOT acknowledged yet)
    │
    ▼
Worker starts processing
    │
    ▼
Worker crashes (OOM, SIGKILL, container restart)
    │
    ▼
Message NOT removed from Redis broker
    │
    ▼
Visibility timeout expires (5 minutes default)
    │
    ▼
Message returned to queue
    │
    ▼
New worker picks up task
    │
    ▼
Idempotency check (Redis + PostgreSQL)
    │
    ▼
If already completed: skip
If processing in progress: skip
If new: process
```

### Configuration

```python
# app/queue/celery_app.py
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
)
```

---

## Future Enhancements

### Multi-Source Support

- Generic webhook endpoint
- Source registration API
- Configurable handlers per source

### Webhook Transformations

- Transform payloads before storage
- Map external schema to internal

### Observability

- Webhook processing latency (histogram)
- Success/failure rates by source (counter)
- Idempotency hits (counter with labels: source, reason)