# Segment Engine

> Dynamic audience filtering and materialization. Last updated: 2026-05-12.

---

## Overview

Segments define reusable dynamic audiences using a JSON-based Filter DSL. Segments can be materialized asynchronously, storing membership in `segment_memberships` for fast lookups.

---

## Filter DSL

### Definition Schema

```json
{
  "op": "and",
  "children": [
    { "op": "eq", "field": "name", "value": "John" },
    { "op": "has_tag", "tag": "vip" },
    { "op": "attr", "key": "lifetime_value", "cmp": "gte", "value": 1000 }
  ]
}
```

### Supported Operators

#### Logical
| Op | Description | Fields |
|----|-------------|--------|
| `and` | All children must match | `children: [Filter]` |
| `or` | Any child must match | `children: [Filter]` |
| `not` | Negate child | `child: Filter` |

#### Field Comparisons
| Op | Fields | Value Type |
|----|--------|------------|
| `eq` | name, phone, created_at | any |
| `neq` | name, phone, created_at | any |
| `contains` | name, phone | string |
| `in` | name, phone | array |
| `gt`, `gte`, `lt`, `lte` | name, phone, created_at | comparable |

#### Tags
| Op | Description | Value |
|----|-------------|-------|
| `has_tag` | Contact has tag | tag name string |

#### Custom Attributes
| Op | Description | Fields |
|----|-------------|--------|
| `attr` | Attribute comparison | `key`, `cmp`, `value` |

### Attribute Comparisons

| Cmp | Meaning | Value Type |
|-----|---------|-------------|
| `eq` | Equal | text, number, boolean |
| `neq` | Not equal | text, number, boolean |
| `contains` | Text contains | string |
| `gt`, `gte`, `lt`, `lte` | Comparison | number |

---

## Architecture

```
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│ Segment    │────▶│ Filter DSL  │────▶│ SQL Compilation │
│ Definition │     │ Validation │     │ (WHERE clause)  │
└─────────────┘     └─────────────┘     └────────┬────────┘
                                                  │
                                                  ▼
┌─────────────┐     ┌─────────────┐     ┌─────────────────┐
│ Membership  │◀────│ Worker      │◀────│ Contact Query   │
│ Table       │     │ (materialize)│     │ (contacts)      │
└─────────────┘     └─────────────┘     └─────────────────┘
```

---

## Filter DSL Compilation

Located in `app/services/segment_filter_dsl.py`.

### Validation

```python
def validate_definition(definition: dict) -> None:
    # Recursive validation
    # Checks op, required fields, value types
    # Raises SegmentDefinitionError on invalid
```

### SQL Compilation

```python
def compile_to_where_clause(workspace_id: int, definition: dict) -> CompiledFilter:
    # Returns CompiledFilter with .where_clause
    # Used in segment_service.materialize_segment_membership
```

### CompiledFilter

```python
@dataclass(frozen=True, slots=True)
class CompiledFilter:
    where_clause: ColumnElement[bool]
```

---

## Materialization

### Trigger Flow

```
POST /segments/{id}/materialize
    ↓
Queue: segments.materialize task
    ↓
Get segment definition
    ↓
Compile DSL to SQL WHERE clause
    ↓
Query matching contacts
    ↓
Clear existing memberships
    ↓
Insert new memberships
    ↓
Update segment.approx_size
    ↓
Set segment.last_materialized_at
```

### Service Layer

`app/services/segment_service.py`:

```python
async def materialize_segment_membership(
    session: AsyncSession,
    workspace_id: int,
    segment: Segment,
) -> int:
    # 1. Compile definition to CompiledFilter
    # 2. Query: SELECT id FROM contacts WHERE workspace_id AND where_clause
    # 3. DELETE FROM segment_memberships WHERE segment_id
    # 4. INSERT segment_memberships for all matching contacts
    # 5. Update segment.approx_size and last_materialized_at
    # 6. Return count
```

---

## Segment Model

```python
class Segment(Base):
    __tablename__ = "segments"
    
    id: Mapped[int]
    workspace_id: Mapped[int]
    name: Mapped[str]                    # UQ within workspace
    status: Mapped[str]                 # active, archived
    definition: Mapped[dict]            # JSONB Filter DSL
    approx_size: Mapped[int]            # Cached membership count
    last_materialized_at: Mapped[datetime | None]
    created_at: Mapped[datetime]
    updated_at: Mapped[datetime]
```

### SegmentMembership

```python
class SegmentMembership(Base):
    __tablename__ = "segment_memberships"
    
    id: Mapped[int]
    workspace_id: Mapped[int]
    segment_id: Mapped[int]
    contact_id: Mapped[int]
    materialized_at: Mapped[datetime]    # When membership was created
```

---

## API Endpoints

### Create Segment

```
POST /segments
{
  "name": "VIP Customers",
  "definition": {
    "op": "and",
    "children": [
      { "op": "has_tag", "tag": "vip" },
      { "op": "attr", "key": "lifetime_value", "cmp": "gte", "value": 1000 }
    ]
  }
}
```

### Preview Segment

```
POST /segments/preview
{
  "definition": { ... }
}
Returns: { "matching_count": 42, "sample_contacts": [...] }
```

### Materialize Segment

```
POST /segments/{id}/materialize
Returns: { "status": "queued", "job_id": "..." }
```

Poll via `GET /celery/{job_id}` for status.

### List Segments

```
GET /segments
Returns: [{ id, name, status, approx_size, last_materialized_at, ... }]
```

---

## Use Cases

### Use Case 1: Tag-Based Segment

```json
{
  "op": "has_tag",
  "tag": "newsletter-subscriber"
}
```

### Use Case 2: High-Value Customers

```json
{
  "op": "and",
  "children": [
    { "op": "has_tag", "tag": "purchased" },
    { "op": "attr", "key": "lifetime_value", "cmp": "gte", "value": 500 }
  ]
}
```

### Use Case 3: Recent + Active

```json
{
  "op": "and",
  "children": [
    { "op": "gt", "field": "created_at", "value": "2026-01-01T00:00:00Z" },
    { "op": "has_tag", "tag": "engaged" }
  ]
}
```

### Use Case 4: Exclude Segment

```json
{
  "op": "and",
  "children": [
    { "op": "has_tag", "tag": "subscriber" },
    { "op": "not", "child": { "op": "has_tag", "tag": "churned" } }
  ]
}
```

---

## Frontend UI (Planned)

### Segment Builder

Visual drag-and-drop segment builder:
- Add conditions (field + operator + value)
- Group with AND/OR
- Nest groups for complex logic
- Preview count before saving

### Segment Management

- List all segments with membership counts
- Materialize on demand
- Schedule periodic materialization (cron)
- Archive unused segments

### Campaign Targeting

- Select segment as campaign audience
- Show estimated reach before sending
- Update audience from segment definition

---

## Performance Considerations

### Indexing

- `contacts.workspace_id` — base filter
- `contacts.name` — text search
- `contacts.phone` — exact match
- `contact_tags.contact_id` — tag lookups
- `contact_attribute_values.contact_id` — attribute lookups
- `segment_memberships.segment_id` — membership lookup

### Materialization Frequency

| Scenario | Frequency |
|----------|-----------|
| Static segment | On-demand only |
| Dynamic segment | Every 1 hour (cron) |
| Real-time need | Materialized views (future) |

### Scaling

For large workspaces (>100K contacts):
- Parallelize contact batch queries
- Use cursor-based pagination
- Batch INSERT memberships
- Consider PostgreSQL `INSERT ... ON CONFLICT` for upserts

---

## Future Enhancements

### Scheduled Materialization
- Cron-based segment refresh
- Separate queue for scheduled tasks
- Notification on materialization complete

### Segment Combinations
- Combine multiple segments (intersection, union, difference)
- Pre-built segment templates

### Predictive Segments
- ML-based propensity scoring
- Behavioral segmentation
- RFM (Recency, Frequency, Monetary)

### Real-Time Segments
- Trigger on contact events
- WebSocket updates to segment membership
- Instant campaign targeting
