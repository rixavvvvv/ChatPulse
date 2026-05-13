# Attribution Strategy

> How ChatPulse tracks and attributes ecommerce conversions to automation touchpoints.

## Overview

The attribution system measures the effectiveness of WhatsApp automation messages in driving conversions. It answers the question: **"Which automation message led to this purchase?"**

## Data Model

```
EcommerceAttribution
├── workspace_id
├── contact_id
├── order_id          ← Shopify order ID
├── cart_id           ← Shopify cart token
├── attribution_model ← first_touch | last_touch | linear | time_decay
├── touchpoints[]     ← Array of interaction records
├── revenue           ← Order total attributed
├── currency
├── converted         ← Boolean
├── conversion_timestamp
├── first_touch_id    ← Execution ID of first interaction
└── last_touch_id     ← Execution ID of last interaction
```

## Touchpoint Structure

Each touchpoint records a single automation interaction:

```json
{
  "execution_id": "uuid-v4",
  "type": "cart_abandoned | order_created | shipment_created | ...",
  "automation_type": "abandoned_cart_recovery",
  "automation_id": 42,
  "template_id": 15,
  "timestamp": "2026-01-15T10:30:00Z",
  "delivered": true,
  "opened": false,
  "clicked": false
}
```

## Attribution Models

### First Touch
Credits the **first** automation message that reached the customer before conversion.

**Use Case:** Understanding which initial outreach drives awareness.

```
Cart Abandoned → Recovery Email (1h) ← CREDITED
                 Recovery Email (24h)
                 Order Placed ✓
```

### Last Touch (Default)
Credits the **last** automation message before conversion.

**Use Case:** Identifying the message that directly triggered the purchase.

```
Cart Abandoned → Recovery Email (1h)
                 Recovery Email (24h) ← CREDITED
                 Order Placed ✓
```

### Linear
Credits **all** automation messages equally.

**Use Case:** Understanding the full journey's contribution.

```
Cart Abandoned → Recovery Email (1h) ← 50% credit
                 Recovery Email (24h) ← 50% credit
                 Order Placed ✓
```

### Time Decay
Credits messages closer to conversion more heavily using exponential decay.

**Use Case:** Balancing recency with journey awareness.

```
Cart Abandoned → Recovery Email (1h) ← 33% credit
                 Recovery Email (24h) ← 67% credit
                 Order Placed ✓
```

## Conversion Detection

Conversion is detected when:

1. A `cart_abandoned` event created automation executions
2. A subsequent `order_created` event arrives for the **same cart token**
3. The orchestrator:
   - Cancels pending cart recovery executions
   - Marks existing attribution records as `converted = true`
   - Sets `conversion_timestamp`
   - Updates `revenue` with order total

## Attribution Window

- **Default window:** 72 hours (configurable per automation)
- Only touchpoints within the window before conversion are considered
- Touchpoints after conversion are excluded

## Revenue Attribution

```python
revenue_per_touchpoint = order_total / touchpoint_count  # Linear model

# Time decay: weight = exp(-lambda * hours_before_conversion)
# First touch: 100% to first touchpoint
# Last touch: 100% to last touchpoint
```

## Analytics Queries

### Recovery Rate
```
recovered_orders / total_abandoned_carts × 100
```

### Conversion Rate per Automation
```
converted_executions / total_executions × 100
```

### Revenue per Automation
```
SUM(attributed_revenue) WHERE automation_id = X
```

### Message Effectiveness
```
delivery_rate = delivered_count / sent_count × 100
recovery_rate = converted_count / delivered_count × 100
```

## Implementation Notes

1. **Touchpoints are append-only** — never modified after creation
2. **Attribution is recalculated** when conversion is detected
3. **Revenue is in the merchant's currency** — no conversion
4. **Multiple automations** can contribute touchpoints to the same conversion
5. **Cart token** is the primary key linking abandonments to orders
