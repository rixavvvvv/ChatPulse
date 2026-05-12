# Analytics Event Storage Architecture

Centralized analytics infrastructure for ChatPulse with append-only event log, pre-computed rollups, and real-time metrics.

## Overview

The analytics system provides:
- Append-only event storage for audit and replay
- Pre-computed rollups for efficient querying
- Real-time metrics for dashboards
- Workspace and campaign-level aggregations
- Eventual consistency with configurable retention

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         ANALYTICS ARCHITECTURE                                │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                    Event Sources                                      │  │
│  │                                                                       │  │
│  │   Messages    │   Webhooks    │   Campaigns    │   Recovery          │  │
│  │      │            │              │               │                     │  │
│  │      └────────────┴──────────────┴───────────────┘                  │  │
│  │                              │                                          │  │
│  │                              ▼                                          │  │
│  │                     ┌────────────────┐                                │  │
│  │                     │  Analytics     │                                │  │
│  │                     │  Ingestion     │                                │  │
│  │                     │  Service        │                                │  │
│  │                     └────────┬───────┘                                │  │
│  └───────────────────────────────│────────────────────────────────────────┘  │
│                                  │                                            │
│                    ┌─────────────┴─────────────┐                            │
│                    │                           │                            │
│                    ▼                           ▼                            │
│         ┌──────────────────┐        ┌──────────────────┐                  │
│         │  Event Log       │        │  Real-time       │                  │
│         │  (analytics_     │        │  Redis Pub/Sub    │                  │
│         │   events)        │        │                  │                  │
│         └────────┬─────────┘        └────────┬─────────┘                  │
│                  │                          │                             │
│                  ▼                          ▼                             │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                  Aggregation Workers                                  │  │
│  │  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐  ┌─────────┐     │  │
│  │  │  1m     │  │  5m     │  │  1h     │  │  1d     │  │Percentile│    │  │
│  │  │ rollup  │  │ rollup  │  │ rollup  │  │ rollup  │  │ calc     │    │  │
│  │  └────┬────┘  └────┬────┘  └────┬────┘  └────┬────┘  └─────────┘    │  │
│  │       └────────────┴────────────┴────────────┘                       │  │
│  │                              │                                         │  │
│  │                              ▼                                         │  │
│  │                     ┌────────────────┐                                │  │
│  │                     │  Rollup Store  │                                │  │
│  │                     │  (analytics_  │                                │  │
│  │                     │   rollups)     │                                │  │
│  │                     └────────┬───────┘                                │  │
│  └───────────────────────────────│───────────────────────────────────────┘  │
│                                  │                                           │
│  ┌───────────────────────────────│────────────────────────────────────────┐ │
│  │                  Query Layer                                          │ │
│  │                                                                       │ │
│  │   Workspace Metrics    │    Campaign Metrics    │    Realtime         │ │
│  │   (workspace_metrics)  │    (campaign_metrics)  │    (realtime_metrics)│ │
│  │                                                                       │ │
│  └────────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Data Models

### AnalyticsEvent (Append-Only Event Log)

Primary source of truth for all analytics data. Events are immutable once written.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| event_id | UUID | Unique event identifier |
| event_type | VARCHAR(100) | Event type (e.g., "message.sent") |
| event_category | VARCHAR(50) | Category (message, webhook, campaign, etc.) |
| occurred_at | TIMESTAMPTZ | When event occurred |
| ingested_at | TIMESTAMPTZ | When event was stored |
| workspace_id | INTEGER | Workspace identifier |
| campaign_id | INTEGER | Optional campaign reference |
| user_id | INTEGER | Optional user reference |
| contact_id | INTEGER | Optional contact reference |
| queue_name | VARCHAR(100) | Optional queue name |
| task_id | VARCHAR(100) | Optional task identifier |
| worker_id | VARCHAR(100) | Optional worker identifier |
| event_data | JSONB | Additional event data |
| value_numeric | FLOAT | Numeric value for aggregation |
| duration_ms | FLOAT | Duration in milliseconds |
| count | INTEGER | Count for aggregation |
| source | VARCHAR(100) | Event source |
| trace_id | VARCHAR(50) | Correlation trace ID |
| success | BOOLEAN | Event outcome |
| error_type | VARCHAR(100) | Error type if failed |
| labels | JSONB | Dimension labels |
| processed | BOOLEAN | Aggregation status |
| processed_at | TIMESTAMPTZ | When aggregated |
| aggregation_key | VARCHAR(200) | Rollup grouping key |

### AnalyticsRollup (Pre-computed Aggregations)

Materialized aggregations from events, updated by workers.

| Column | Type | Description |
|--------|------|-------------|
| id | BIGSERIAL | Primary key |
| workspace_id | INTEGER | Workspace identifier |
| rollup_key | VARCHAR(200) | Grouping key |
| granularity | VARCHAR(10) | Time granularity (1m, 5m, 1h, 1d) |
| window_start | TIMESTAMPTZ | Time window start |
| window_end | TIMESTAMPTZ | Time window end |
| event_type | VARCHAR(100) | Event type |
| event_category | VARCHAR(50) | Category |
| total_count | BIGINT | Total events |
| success_count | BIGINT | Successful events |
| failure_count | BIGINT | Failed events |
| value_sum | FLOAT | Sum of values |
| value_avg | FLOAT | Average value |
| duration_sum | FLOAT | Sum of durations |
| duration_avg | FLOAT | Average duration |
| duration_p50/p95/p99 | FLOAT | Percentiles |
| unique_contacts | BIGINT | Unique contacts |
| unique_campaigns | BIGINT | Unique campaigns |

### WorkspaceMetrics (Daily Aggregations)

Per-workspace daily metrics for dashboards.

| Column | Type | Description |
|--------|------|-------------|
| workspace_id | INTEGER | Workspace identifier |
| period_start | TIMESTAMPTZ | Period start |
| period_end | TIMESTAMPTZ | Period end |
| messages_sent/delivered/failed | BIGINT | Message counts |
| campaigns_created/completed/failed | BIGINT | Campaign counts |
| webhooks_received/processed/failed | BIGINT | Webhook counts |
| recoveries_detected/completed/failed | BIGINT | Recovery counts |
| rate_limit_allowed/rejected | BIGINT | Rate limit counts |

### CampaignMetrics (Campaign Aggregations)

Per-campaign metrics for campaign analysis.

| Column | Type | Description |
|--------|------|-------------|
| campaign_id | INTEGER | Campaign identifier |
| sent/delivered/read/failed | INTEGER | Recipient counts |
| delivery/read/failure_rate | FLOAT | Computed rates |
| avg/min/max_per_recipient_ms | FLOAT | Duration stats |
| hourly_counts | JSONB | Hourly distribution |
| error_breakdown | JSONB | Error by type |
| recovery_count/success_count | INTEGER | Recovery stats |

## Event Types

### Message Events
- `message.sent` - Message dispatched
- `message.delivered` - Message delivered
- `message.failed` - Message failed
- `message.read` - Message read

### Webhook Events
- `webhook.received` - Webhook received
- `webhook.processed` - Webhook processed
- `webhook.failed` - Webhook failed

### Campaign Events
- `campaign.created` - Campaign created
- `campaign.started` - Campaign started
- `campaign.completed` - Campaign completed
- `campaign.failed` - Campaign failed

### Recovery Events
- `recovery.detected` - Stale campaign detected
- `recovery.started` - Recovery started
- `recovery.completed` - Recovery completed
- `recovery.failed` - Recovery failed

### Queue Events
- `queue.task.started` - Task started
- `queue.task.completed` - Task completed
- `queue.task.failed` - Task failed

## Aggregation Strategy

### Time-based Rollups

| Granularity | Window | Retention | Use Case |
|-------------|--------|-----------|----------|
| 1m | 1 minute | 7 days | Real-time monitoring |
| 5m | 5 minutes | 30 days | Short-term trends |
| 1h | 1 hour | 90 days | Daily analysis |
| 1d | 1 day | 365 days | Historical trends |

### Aggregation Pipeline

1. **Raw Events** → ingested into `analytics_events`
2. **1m Rollup** → aggregated every minute
3. **5m Rollup** → aggregated every 5 minutes
4. **1h Rollup** → aggregated every hour
5. **1d Rollup** → aggregated every day

### Aggregation SQL Pattern

```sql
-- Aggregate into rollups
INSERT INTO analytics_rollups (
    workspace_id, rollup_key, granularity,
    window_start, window_end, event_type,
    total_count, success_count, failure_count,
    value_sum, value_avg, duration_avg
)
SELECT
    workspace_id,
    aggregation_key,
    :granularity,
    :window_start,
    :window_end,
    event_type,
    COUNT(*) as total_count,
    SUM(CASE WHEN success THEN 1 ELSE 0 END),
    SUM(CASE WHEN NOT success THEN 1 ELSE 0 END),
    COALESCE(SUM(value_numeric), 0),
    COALESCE(AVG(value_numeric), 0),
    COALESCE(AVG(duration_ms), 0)
FROM analytics_events
WHERE processed = false
    AND occurred_at >= :window_start
    AND occurred_at < :window_end
GROUP BY workspace_id, event_type, aggregation_key
ON CONFLICT DO NOTHING;

-- Mark as processed
UPDATE analytics_events
SET processed = true, processed_at = :now
WHERE processed = false
    AND occurred_at >= :window_start
    AND occurred_at < :window_end;
```

## Partitioning Strategy

### Event Log Partitioning

```sql
-- Partition by month
CREATE TABLE analytics_events (
    ...
) PARTITION BY RANGE (occurred_at);

-- Create monthly partitions
CREATE TABLE analytics_events_2024_01 PARTITION OF analytics_events
    FOR VALUES FROM ('2024-01-01') TO ('2024-02-01');

CREATE TABLE analytics_events_2024_02 PARTITION OF analytics_events
    FOR VALUES FROM ('2024-02-01') TO ('2024-03-01');

-- Add new partitions automatically via scheduled task
```

### Benefits
- Efficient range queries on time-based filters
- Easy partition-level cleanup for retention
- Improved query performance for recent data

## Indexing Strategy

### Primary Indexes

```sql
-- Time-based queries (most common)
CREATE INDEX ix_analytics_events_occurred_at ON analytics_events (occurred_at);
CREATE INDEX ix_analytics_events_workspace_time ON analytics_events (workspace_id, occurred_at);
CREATE INDEX ix_analytics_events_campaign_time ON analytics_events (campaign_id, occurred_at);

-- Type-based queries
CREATE INDEX ix_analytics_events_type ON analytics_events (event_type);
CREATE INDEX ix_analytics_events_category ON analytics_events (event_category);

-- Processing status (for aggregation workers)
CREATE INDEX ix_analytics_events_processed ON analytics_events (processed, occurred_at);

-- Rollup indexes
CREATE INDEX ix_rollups_workspace_window ON analytics_rollups (workspace_id, window_start);
CREATE INDEX ix_rollups_key_window ON analytics_rollups (rollup_key, window_start);
```

## Retention Policy

| Table | Raw Retention | Rollup Retention |
|-------|---------------|------------------|
| analytics_events | 90 days (processed) | N/A |
| analytics_rollups (1m) | 7 days | Permanent |
| analytics_rollups (5m) | 30 days | Permanent |
| analytics_rollups (1h) | 90 days | Permanent |
| analytics_rollups (1d) | 365 days | Permanent |
| workspace_metrics | N/A | 2 years |
| campaign_metrics | N/A | 2 years |
| realtime_metrics | N/A | 24 hours |

### Cleanup SQL

```sql
-- Raw events older than 90 days
DELETE FROM analytics_events
WHERE occurred_at < NOW() - INTERVAL '90 days'
    AND processed = true;

-- 1m rollups older than 7 days
DELETE FROM analytics_rollups
WHERE granularity = '1m'
    AND window_end < NOW() - INTERVAL '7 days';
```

## Ingestion Pipeline

### Synchronous Ingestion (Low Latency)

```python
async def ingest_event(event_data: dict) -> str:
    event = AnalyticsEvent(...)
    await session.add(event)
    await session.commit()

    # Publish to Redis for real-time consumers
    await redis.publish(f"analytics:events:{category}", message)

    return str(event.event_id)
```

### Asynchronous Ingestion (High Volume)

```python
@shared_task
def ingest_event_task(event_data: dict):
    # Use Celery for async processing
    event = AnalyticsEvent(...)
    session.add(event)
    session.commit()

    return event.event_id

# Batch ingestion
@shared_task
def ingest_batch_task(events: list):
    for event in events:
        session.add(AnalyticsEvent(**event))
    session.commit()
```

### Event Factory Patterns

```python
# From message events
await AnalyticsEventFactory.from_message_event(
    workspace_id=1,
    campaign_id=123,
    event_type="message.sent",
    success=True,
    duration_ms=45.2,
)

# From webhook events
await AnalyticsEventFactory.from_webhook_event(
    workspace_id=1,
    source="meta",
    event_type="webhook.received",
)

# From campaign events
await AnalyticsEventFactory.from_campaign_event(
    workspace_id=1,
    campaign_id=123,
    event_type="campaign.completed",
    recipient_count=1000,
    duration_ms=60000.0,
)
```

## API Endpoints

### Event Queries
- `GET /analytics/events` - List events with filtering
- `GET /analytics/events/count` - Count events in time range
- `GET /analytics/rollups` - List pre-computed rollups

### Workspace Metrics
- `GET /analytics/workspace` - Get workspace metrics
- `GET /analytics/workspace/dashboard` - Get dashboard summary

### Campaign Metrics
- `GET /analytics/campaign/{id}` - Get campaign metrics

### Real-time
- `GET /analytics/realtime` - Get real-time metrics
- `POST /analytics/realtime/update` - Update real-time metrics

### Ingestion
- `POST /analytics/ingest` - Ingest single event
- `POST /analytics/ingest/batch` - Ingest batch events

## Query Examples

### Get Campaign Performance

```sql
SELECT
    campaign_id,
    COUNT(*) FILTER (WHERE event_type = 'message.sent') as sent,
    COUNT(*) FILTER (WHERE event_type = 'message.delivered') as delivered,
    COUNT(*) FILTER (WHERE event_type = 'message.failed') as failed,
    AVG(duration_ms) FILTER (WHERE event_type = 'message.sent') as avg_time
FROM analytics_events
WHERE campaign_id = :campaign_id
    AND occurred_at >= :start_time
    AND occurred_at < :end_time
GROUP BY campaign_id;
```

### Get Hourly Message Trend

```sql
SELECT
    date_trunc('hour', occurred_at) as hour,
    COUNT(*) FILTER (WHERE event_type = 'message.sent') as sent,
    COUNT(*) FILTER (WHERE event_type = 'message.delivered') as delivered
FROM analytics_events
WHERE workspace_id = :workspace_id
    AND event_type LIKE 'message.%'
    AND occurred_at >= NOW() - INTERVAL '24 hours'
GROUP BY date_trunc('hour', occurred_at)
ORDER BY hour;
```

### Get Error Breakdown

```sql
SELECT
    error_type,
    COUNT(*) as count
FROM analytics_events
WHERE workspace_id = :workspace_id
    AND success = false
    AND occurred_at >= :start_time
GROUP BY error_type
ORDER BY count DESC;
```

## Performance Characteristics

| Operation | Latency | Notes |
|-----------|---------|-------|
| Ingest event (sync) | 10-50ms | Single event |
| Ingest batch | 100-500ms | Per batch |
| Query events | 50-200ms | With filters |
| Query rollups | 10-50ms | Pre-computed |
| Aggregation | 1-5s | Per granularity |

## Monitoring Recommendations

### Key Dashboards

1. **Event Ingestion**
   - Events per second by category
   - Ingestion latency P50/P95/P99
   - Failed ingestions

2. **Aggregation Health**
   - Unprocessed event backlog
   - Aggregation job duration
   - Rollup completeness

3. **Workspace Activity**
   - Messages per workspace per day
   - Campaign success rates
   - Webhook volume

### Alert Thresholds

| Metric | Warning | Critical |
|--------|---------|----------|
| Unprocessed events | > 10000 | > 50000 |
| Ingestion latency P99 | > 500ms | > 2000ms |
| Aggregation job duration | > 60s | > 300s |
| Failed events rate | > 1% | > 5% |

## Eventual Consistency

The analytics system uses eventual consistency:

### Write Path
1. Events written to raw log immediately
2. Events marked as unprocessed
3. Aggregation workers process in batches
4. Events marked as processed

### Consistency Guarantees
- **Write**: At-least-once (events may be duplicated on retry)
- **Read**: Eventual consistency (< 5 minute lag for rollups)
- **Accuracy**: Counts may be slightly overestimated due to dedup handling

### Conflict Resolution
- Rollup inserts use `ON CONFLICT DO NOTHING`
- Rollup updates use `ON CONFLICT DO UPDATE`
- Counter updates use atomic increments