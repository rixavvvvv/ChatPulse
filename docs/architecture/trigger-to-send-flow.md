# Trigger-to-Send Flow

> Technical reference for the complete message path from Shopify event to WhatsApp delivery.

## Sequence Diagram

```
Shopify        Webhook Route    Orchestrator    Automation     Delayed       Dispatch      WhatsApp
  │                │                │            Service        Exec           Service       API
  │                │                │              │             │               │             │
  │ POST /webhook  │                │              │             │               │             │
  ├───────────────►│                │              │             │               │             │
  │                │ verify HMAC    │              │             │               │             │
  │                │ ingest         │              │             │               │             │
  │                │                │              │             │               │             │
  │                │ Celery task    │              │             │               │             │
  │                ├───────────────►│              │             │               │             │
  │                │                │              │             │               │             │
  │                │                │ map topic    │             │               │             │
  │                │                │ → trigger    │             │               │             │
  │                │                │              │             │               │             │
  │                │                │ find active  │             │               │             │
  │                │                ├─────────────►│             │               │             │
  │                │                │ automations  │             │               │             │
  │                │                │◄─────────────┤             │               │             │
  │                │                │              │             │               │             │
  │                │                │ create exec  │             │               │             │
  │                │                ├─────────────►│             │               │             │
  │                │                │              │             │               │             │
  │                │           [delayed?]          │             │               │             │
  │                │                │──────────────┼────────────►│               │             │
  │                │                │              │  schedule   │               │             │
  │                │                │              │             │               │             │
  │                │                │              │    ...time passes...        │             │
  │                │                │              │             │               │             │
  │                │                │              │  lease      │               │             │
  │                │                │              │◄────────────┤               │             │
  │                │                │              │             │               │             │
  │                │                │              │  execute    │               │             │
  │                │                │              ├─────────────┼──────────────►│             │
  │                │                │              │             │               │             │
  │                │                │              │             │    send_template            │
  │                │                │              │             │               ├────────────►│
  │                │                │              │             │               │             │
  │                │                │              │             │               │  wamid      │
  │                │                │              │             │               │◄────────────┤
  │                │                │              │             │               │             │
  │                │                │              │  update     │               │             │
  │                │                │              │  execution  │               │             │
  │                │                │              │  status=sent│               │             │
```

## Key Components

### 1. Webhook Route (`app/routes/webhook_order.py`)
- Receives raw Shopify payload
- Verifies HMAC signature
- Creates `WebhookIngestion` record
- Dispatches Celery task

### 2. Orchestrator (`app/services/ecommerce_orchestrator_service.py`)
- Maps Shopify topic → internal trigger type
- Resolves customer phone to contact
- Checks for cart→order conversion (cancels pending recovery)
- Detects COD payment method
- Finds matching active automations
- Creates execution records
- Routes to immediate or delayed path

### 3. Automation Service (`app/services/ecommerce_automation_service.py`)
- CRUD for automations
- Execution lifecycle management
- Attribution tracking
- Analytics queries

### 4. Delayed Execution (`app/services/delayed_execution_service.py`)
- Schedules future execution
- Lease-based locking for crash safety
- Business hours awareness
- Expiration handling

### 5. Dispatch Service (`app/services/message_dispatch_service.py`)
- Sends WhatsApp template messages
- Retry classification
- Error categorization
- Delivery tracking

## Idempotency Guarantees

| Component | Mechanism |
|-----------|-----------|
| Webhook ingestion | `X-Shopify-Webhook-Id` dedup |
| Task execution | Redis-based `IdempotencyMixin` |
| Delayed execution | Lease-based locking (`ExecutionLease`) |
| Message sending | `provider_message_id` tracking |

## Error Recovery Paths

| Failure Point | Recovery |
|---------------|----------|
| Webhook route crash | Shopify auto-retries (up to 19 times) |
| Celery task crash | Late ACK + `reject_on_worker_lost` → requeue |
| Delayed execution missed | Lease timeout → another worker picks up |
| WhatsApp API error | Exponential backoff retry (max 3) |
| All retries exhausted | Dead letter queue + execution status=failed |
