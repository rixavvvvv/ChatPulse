# Ecommerce Automation Lifecycle

> Architecture reference for the ChatPulse ecommerce automation engine.

## Overview

The ecommerce automation system processes Shopify webhook events and triggers automated WhatsApp messages at the right moment in the customer journey.

## Lifecycle Stages

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   SHOPIFY    │     │  ORCHESTRATOR │     │   EXECUTION  │     │   DISPATCH   │
│   WEBHOOK    │────▶│   SERVICE     │────▶│   ENGINE     │────▶│   SERVICE    │
│              │     │              │     │              │     │              │
│  order/create│     │ topic→trigger│     │ delayed/     │     │ send_template│
│  carts/update│     │ match autos  │     │ immediate    │     │ with_tracking│
│  fulfillments│     │ validate seg │     │ retry logic  │     │              │
│  orders/paid │     │ create exec  │     │ idempotency  │     │              │
└──────────────┘     └──────────────┘     └──────────────┘     └──────────────┘
                                                                       │
                                                                       ▼
                                                              ┌──────────────┐
                                                              │ ATTRIBUTION  │
                                                              │   TRACKER    │
                                                              │              │
                                                              │ touchpoints  │
                                                              │ revenue      │
                                                              │ conversion   │
                                                              └──────────────┘
```

## Stage 1: Webhook Ingestion

**Entry Points:**
- `POST /webhooks/shopify` — Shopify webhook receiver
- HMAC signature verification
- Idempotent ingestion (dedup via `X-Shopify-Webhook-Id`)

**Shopify Topics → Internal Triggers:**

| Shopify Topic | Internal Trigger | Automation Type |
|---------------|-----------------|-----------------|
| `orders/create` | `order_created` | Order Confirmation |
| `orders/create` (COD) | `cod_pending` | COD Verification |
| `orders/cancelled` | `order_cancelled` | — |
| `checkouts/update` | `cart_abandoned` | Abandoned Cart Recovery |
| `fulfillments/create` | `shipment_created` | Shipment Updates |
| `fulfillments/update` (delivered) | `shipment_delivered` | Delivery Notification |
| `orders/paid` | `payment_received` | Payment Confirmation |

## Stage 2: Orchestration

The **EcommerceOrchestratorService** is the central brain:

1. **Map** the Shopify topic to an internal trigger type
2. **Resolve** the customer phone → contact record
3. **Cart Conversion Check** — if `order_created`, cancel any pending `cart_abandoned` executions
4. **COD Detection** — if payment gateway is `cod`, remap to `cod_pending` trigger
5. **Match Automations** — find all active automations matching the trigger type
6. **Segment Validation** — if automation has a segment filter, verify contact membership
7. **Dispatch** — create execution record and queue immediate or delayed processing

## Stage 3: Execution

Two execution paths:

### Immediate Execution
- Automation `delay_seconds == 0`
- Celery task `ecommerce.execute_automation` dispatched immediately
- Template message sent via `whatsapp_service.send_template_message`

### Delayed Execution
- Automation `delay_seconds > 0`
- `DelayedExecution` record created with lease-based locking
- Worker polls for due executions
- Lease acquired → execution proceeds
- If worker crashes → lease expires → another worker picks up

## Stage 4: Delivery & Tracking

- Message sent via Meta WhatsApp Business API
- `MessageTracking` record created with `provider_message_id`
- Delivery status webhooks update tracking status
- Execution status updated: `sent` → `delivered` or `failed`

## Stage 5: Attribution

After successful execution:
- **Touchpoint** recorded with execution_id, automation_type, timestamp
- **Attribution Model** applied (first_touch, last_touch, linear, time_decay)
- **Revenue** attributed when order value is available
- **Conversion** flag set when cart_abandoned → order_created detected

## Error Handling

```
Execution Failed
       │
       ▼
  retry_count < max_retries?
       │
  YES: increment retry_count
       schedule retry with exponential backoff
       │
  NO:  mark execution as FAILED
       log to dead letter queue
       alert via monitoring
```

## Supported Automation Types

| Type | Trigger | Default Delay | Description |
|------|---------|--------------|-------------|
| `abandoned_cart_recovery` | `cart_abandoned` | 1-24 hours | Recovery reminder with cart items |
| `order_confirmation` | `order_created` | Immediate | Order details + estimated delivery |
| `shipment_updates` | `shipment_created` | Immediate | Tracking number + carrier info |
| `delivered_notifications` | `shipment_delivered` | Immediate | Delivery confirmation |
| `cod_verification` | `cod_pending` | 12-24 hours | Payment reminder for COD orders |
| `post_purchase_followup` | `shipment_delivered` | 7 days | Satisfaction check |
| `review_request` | `shipment_delivered` | 14 days | Product review request |
