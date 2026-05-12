# Dashboard Query Infrastructure

> Architecture documentation for ChatPulse analytics dashboard system.
> Generated: 2026-05-12

---

## Overview

The dashboard query infrastructure provides a high-performance, real-time-ready analytics layer for ChatPulse. It delivers campaign delivery metrics, workspace usage metrics, queue health, webhook health, retry analytics, and recovery analytics through a unified API with built-in caching, pagination, filtering, and aggregation granularity support.

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                        Dashboard API Layer                       │
│                   (app/routes/dashboard.py)                      │
│                                                                 │
│  GET /dashboard/campaigns/{id}/delivery                         │
│  GET /dashboard/campaigns/delivery                              │
│  GET /dashboard/workspace/usage                                 │
│  GET /dashboard/queue/health                                    │
│  GET /dashboard/webhooks/health                                  │
│  GET /dashboard/analytics/retry                                 │
│  GET /dashboard/analytics/recovery                              │
│  GET /dashboard/overview                                        │
│  GET /dashboard/alerts                                          │
│  GET /dashboard/realtime                                        │
│  GET /dashboard/realtime/stream  (SSE)                          │
│  POST /dashboard/cache/invalidate                               │
│  GET /dashboard/cache/stats                                      │
└──────────────────────┬──────────────────────────────────────────┘
                       │
                       ▼
┌─────────────────────────────────────────────────────────────────┐
│                    Dashboard Query Service                       │
│               (app/services/dashboard/query_service.py)          │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐    │
│  │  get_campaign_delivery()   — per-campaign metrics       │    │
│  │  get_campaign_delivery_list() — all campaigns           │    │
│  │  get_workspace_usage()    — workspace-level stats      │    │
│  │  get_queue_health()       — task processing rates       │    │
│  │  get_webhook_health()     — webhook processing rates    │    │
│  │  get_retry_analytics()    — retry rates & breakdowns    │    │
│  │  get_recovery_analytics() — recovery operation stats    │    │
│  │  get_dashboard_overview() — summary with comparisons     │    │
│  │  get_realtime_metrics()  — live metrics (5s TTL)       │    │
│  │  get_alerts()             — threshold-based alerts       │    │
│  └─────────────────────────────────────────────────────────┘    │
└──────────────────────┬──────────────────────────────────────────┘
                       │
        ┌───────────────┼───────────────┐
        ▼               ▼               ▼
┌───────────────┐ ┌───────────────┐ ┌───────────────┐
│ Redis Cache   │ │ PostgreSQL    │ │ Redis Pub/Sub │
│ (stale-while- │ │ (source of    │ │ (realtime     │
│  revalidate)  │ │  truth)       │ │  broadcasts)  │
└───────────────┘ └───────────────┘ └───────────────┘
```

---

## Components

### 1. Query Builder (`app/services/dashboard/query_builder.py`)

Utility layer for constructing optimized queries.

| Module | Purpose |
|--------|---------|
| `PaginationInput` / `build_pagination()` | Cursor-aware pagination with `limit`, `offset`, `total`, `has_more` |
| `resolve_date_range()` | Resolves `period` strings (`today`, `last_7_days`, etc.) or explicit `start_time`/`end_time` into a `DateRangeResult` |
| `get_bucket_interval()` | Selects optimal aggregation granularity based on date range length |
| `granularity_to_trunc_unit()` | Maps `1m`/`5m`/`15m`/`1h`/`1d`/`1w` to PostgreSQL `date_trunc` units |
| `compile_filters()` | Builds SQLAlchemy WHERE conditions from a `FilterSpec` |
| `estimate_query_complexity()` | Scores queries as `low`/`medium`/`high`/`extreme` for optimization decisions |
| `should_use_materialized_view()` | Decides whether to use rollup tables vs. raw events |

### 2. Caching Layer (`app/services/dashboard/cache.py`)

Redis-based cache with stale-while-revalidate semantics.

```
Cache Key Pattern:
  chatpulse:dashboard:{scope}:{metric_type}:{workspace_id}:{params_hash}

TTLs per metric type (seconds):
  ┌──────────────────────┬───────┬────────────┐
  │ Metric Type          │ Fresh │ Stale      │
  ├──────────────────────┼───────┼────────────┤
  │ campaign_delivery    │  30   │  120       │
  │ workspace_usage       │  60   │  300       │
  │ queue_health          │  15   │   60       │
  │ webhook_health        │  30   │  120       │
  │ retry_analytics       │ 120   │  600       │
  │ recovery_analytics    │ 120   │  600       │
  │ dashboard_overview    │  60   │  300       │
  │ realtime              │   5   │   15       │
  └──────────────────────┴───────┴────────────┘
```

**Features:**
- Local in-memory LRU cache (100 entries) + Redis distributed cache
- Stale-while-revalidate: returns stale data while triggering background recompute
- Workspace-scoped invalidation: `invalidate_workspace(workspace_id)` clears all keys for a workspace
- Bulk warming: `warm([(key, compute_fn), ...])` pre-populates cache

### 3. Query Service (`app/services/dashboard/query_service.py`)

Main service implementing all metric queries. All methods:
- Accept `start_time`/`end_time`/`period` for date filtering
- Support `granularity` for timeline aggregation
- Use Redis caching with workspace-scoped keys
- Query `message_tracking`, `campaign_contacts`, `campaigns`, `webhook_ingestions`, `analytics_events`, and `queue_dead_letters` tables

**Data Sources:**

| Metric Type | Primary Tables | Composite Indexes Used |
|------------|----------------|----------------------|
| Campaign Delivery | `message_tracking`, `campaign_contacts` | `ix_message_tracking_workspace_status`, `ix_campaign_contacts_campaign` |
| Workspace Usage | `message_tracking`, `campaigns` | `ix_campaigns_workspace_status` |
| Queue Health | `analytics_events`, `queue_dead_letters` | `ix_analytics_events_workspace_category_processed` |
| Webhook Health | `webhook_ingestions` | `ix_webhook_ingestions_source_status` |
| Retry Analytics | `message_tracking` | Same as campaign delivery |
| Recovery Analytics | `analytics_events`, `campaigns` | `ix_analytics_events_campaign_time`, `ix_campaigns_status_heartbeat` |

### 4. Real-time Pub/Sub (`app/services/dashboard/realtime.py`)

Redis pub/sub for live dashboard updates.

```
Channel Architecture:
  chatpulse:ws:{workspace_id}      — workspace-scoped broadcasts
  chatpulse:campaign:{campaign_id}   — campaign-scoped broadcasts
  chatpulse:queue                   — system-wide queue events
  chatpulse:system                  — system announcements

Event Types:
  metric.update        — generic metric change
  campaign.progress    — campaign send progress
  queue.status        — queue depth/worker changes
  alert               — threshold breach alert
  heartbeat           — keepalive (every 30s)

SSE Endpoint:
  GET /dashboard/realtime/stream
  Returns Server-Sent Events stream with:
    event: metric.update
    event: campaign.progress
    event: alert
    event: heartbeat
```

**Publishing from workers:**
```python
from app.services.dashboard.realtime import get_realtime_service

realtime = get_realtime_service()

# Campaign progress
await realtime.publish_campaign_progress(
    workspace_id=1,
    campaign_id=42,
    sent=500,
    delivered=450,
    failed=10,
    total=1000,
)

# Alert
await realtime.publish_alert(
    workspace_id=1,
    alert_id="delivery_low",
    severity="warning",
    message="Delivery rate dropped below 80%",
    metric_name="delivery_rate",
    current_value=75.0,
    threshold=80.0,
)
```

---

## Query Optimization

### For Large Workspaces

1. **Date range constraints**: All queries default to bounded ranges. Explicit `start_time`/`end_time` required for long queries.
2. **Composite indexes**: The schema uses `(workspace_id, occurred_at)` and `(campaign_id, occurred_at)` indexes for time-filtered queries.
3. **Aggregation rollups**: For date ranges > 7 days, queries should use `analytics_rollups` pre-computed tables instead of raw event logs. The `should_use_materialized_view()` helper determines this.
4. **Limit enforcement**: `LIMIT 1000` hard cap on all list queries.

### For High Event Volume

1. **Redis caching**: Short TTLs (5-120s) prevent hot queries from hitting the database repeatedly.
2. **Local LRU cache**: In-process cache with 100-entry limit reduces Redis round-trips.
3. **Async queries**: All database operations are async via SQLAlchemy 2.0 async engine.
4. **Batch operations**: Event ingestion supports batch inserts (`ingest_batch`).

### For Long Time Ranges

1. **Adaptive granularity**: `get_bucket_interval()` automatically selects coarser granularity for longer ranges:
   - ≤ 1 day → 5m buckets
   - 2–7 days → 1h buckets
   - 8–30 days → 1d buckets
   - > 30 days → 1w buckets
2. **Rollup tables**: Pre-computed hourly/daily/weekly aggregations in `analytics_rollups` for historical queries.
3. **Query timeout scaling**: `get_query_timeout()` returns 5s/15s/30s/60s based on complexity.

---

## API Reference

All endpoints are under `/dashboard` and require workspace authentication.

### Campaign Delivery

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/campaigns/{id}/delivery` | GET | Per-campaign delivery metrics with timeline |
| `/dashboard/campaigns/delivery` | GET | List all campaigns with delivery metrics |

**Query Parameters:**
- `start_time`, `end_time` — explicit date range
- `period` — `today`, `yesterday`, `last_7_days`, `last_30_days`, `last_90_days`
- `granularity` — `1m`, `5m`, `15m`, `1h`, `1d`, `1w`
- `include_timeline` — include time-series data (default: true)
- `include_error_breakdown` — include error categorization (default: true)
- `limit`, `offset` — pagination

### Workspace Usage

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/workspace/usage` | GET | Workspace-level message, campaign, contact metrics |

### Queue & Webhook Health

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/queue/health` | GET | Task processing rates, failure rates, worker distribution |
| `/dashboard/webhooks/health` | GET | Webhook processing rates, recent failures |

### Analytics

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/analytics/retry` | GET | Retry rates, error breakdowns, by-campaign stats |
| `/dashboard/analytics/recovery` | GET | Recovery operation stats, recent recoveries |

### Overview & Real-time

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/overview` | GET | Summary metrics with optional period comparison |
| `/dashboard/alerts` | GET | Active alerts from metric thresholds |
| `/dashboard/realtime` | GET | Live metrics (active campaigns, messages in flight) |
| `/dashboard/realtime/stream` | GET | SSE stream for real-time updates |

### Cache Management

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/dashboard/cache/invalidate` | POST | Clear cache for workspace or metric type |
| `/dashboard/cache/stats` | GET | Cache hit/miss statistics |

---

## Data Models

### Message Tracking (delivery metrics source)
```sql
message_tracking (workspace_id, campaign_id, current_status, sent_at, delivered_at, read_at, failed_at, last_error)
-- Indexes: (workspace_id, created_at), (campaign_id, created_at)
```

### Analytics Events (event log)
```sql
analytics_events (event_type, event_category, workspace_id, campaign_id, occurred_at, success, error_type, duration_ms, labels)
-- Indexes: (workspace_id, occurred_at), (campaign_id, occurred_at), (event_type, workspace_id)
```

### Analytics Rollups (pre-computed)
```sql
analytics_rollups (workspace_id, rollup_key, granularity, window_start, event_type, total_count, success_count, failure_count, duration_avg)
-- Indexes: (workspace_id, granularity, window_start), (rollup_key, granularity, window_start)
```

---

## Integration with Existing Infrastructure

### With Analytics Event Storage
The dashboard query service uses the existing `AnalyticsEvent`, `AnalyticsRollup`, `WorkspaceMetrics`, `CampaignMetrics`, and `RealtimeMetrics` models from `app/models/analytics.py`.

### With Campaign Recovery
Campaign recovery data is pulled from both `campaigns` table (recovery_count, last_recovered_at) and `analytics_events` with `event_category = "recovery"`.

### With Webhook Infrastructure
Webhook health metrics query `webhook_ingestions` table, which already has source, status, and error tracking.

### With Queue Infrastructure
Queue health metrics combine `analytics_events` (for successful task lifecycle) with `queue_dead_letters` (for failed tasks).

---

## What's Not Built (Frontend)

- No React/Next.js dashboard frontend yet
- No WebSocket connection from frontend (SSE endpoint is ready, needs client integration)
- No polling infrastructure for frontend (SSE is preferred over polling)
- No alerting email/push notifications
- No scheduled rollup workers (rollup tables are defined but not populated by workers yet)

---

## Running

```bash
# Install new dependencies
pip install redis>=5.0.0 sse-starlette>=2.0.0

# API (includes dashboard routes)
uvicorn app.main:app --reload

# Dashboard routes available at:
# GET  /dashboard/campaigns/{id}/delivery
# GET  /dashboard/workspace/usage
# GET  /dashboard/queue/health
# GET  /dashboard/webhooks/health
# GET  /dashboard/analytics/retry
# GET  /dashboard/analytics/recovery
# GET  /dashboard/overview
# GET  /dashboard/alerts
# GET  /dashboard/realtime
# GET  /dashboard/realtime/stream  (SSE)
```
