# Atomic Rate Limiting Architecture

Redis-based sliding-window rate limiting with atomic Lua scripts for safe concurrent operation.

## Overview

The rate limiting system uses Redis sorted sets with Lua scripts to implement atomic sliding-window rate limiting. This prevents race conditions when multiple workers process messages concurrently.

## Atomicity Guarantees

### The Problem

Traditional multi-step Redis operations have race conditions:

```python
# VULNERABLE - Race condition between check and add
pipe.zremrangebyscore(key, 0, now - window_ms)  # Step 1: Clean old
pipe.zcard(key)                                    # Step 2: Count
count = await pipe.execute()                      # Step 3: Get count

if count < limit:                                 # Step 4: Check
    await redis.zadd(key, {event: now})           # Step 5: Add
```

Between steps 2-5, another worker can add entries, causing over-limit.

### The Solution

Lua scripts execute atomically on the Redis server:

```lua
-- All operations happen without interruption
redis.call('ZREMRANGEBYSCORE', key, '-inf', window_start)
local count = redis.call('ZCARD', key)

if count < max_events then
    redis.call('ZADD', key, now, event_id)
    return {1, count + 1, 0}  -- Allowed
else
    return {0, count, retry_after}  -- Rejected
end
```

### Guarantees

| Guarantee | Description |
|-----------|-------------|
| **Atomicity** | All operations in script execute as single unit |
| **Consistency** | Count reflects exact state at decision time |
| **Isolation** | No intermediate states visible to other clients |
| **No Over-limit** | Enforced limit is never exceeded |

## Redis Script Lifecycle

### 1. Registration

Scripts are registered once at application startup:

```python
async def init_rate_limit_scripts(redis: Redis) -> None:
    _scripts.load_all(redis)  # Registers all Lua scripts
```

Registration returns a script object that can be called repeatedly.

### 2. Script Storage

Redis stores compiled scripts by SHA hash. Subsequent calls use SHA:

```
Redis: SCRIPT LOAD <lua_code>
      -> "abc123def456..."  (SHA digest)

Redis: EVALSHA "abc123def456..." <keys> <args>
```

### 3. Script Execution Flow

```
Worker                     Redis
   |                          |
   |---EVALSHA sha, keys, --->|
   |     args                 |---> Execute Lua
   |                          |     (atomic)
   |                          |---> Return result
   |<--{allowed, count, ------|
        retry_after}          |
```

### 4. TTL Management

Keys are created with 2x TTL to ensure cleanup:

```lua
local current_ttl = redis.call('TTL', key)
if current_ttl == -1 or current_ttl == -2 then
    redis.call('EXPIRE', key, ttl_seconds)
end
```

- `-1`: Key has no expiry (shouldn't happen, but guard anyway)
- `-2`: Key doesn't exist (first entry needs TTL)

## Distributed Concurrency Handling

### Multiple Workers

```
Worker 1                          Worker 2
   |                                 |
   |--EVALSHA (atomic)----------->|
   |   key: queue:rate_limit:123   |
   |   count=19, limit=20          |
   |   -> ADD, return {1,20,0}     |
   |                              |--EVALSHA (atomic)
   |                              |   key: queue:rate_limit:123
   |                              |   count=20, limit=20
   |                              |   -> REJECT, {0,20,1000}
   |<--{1, 20, 0}-----------------|
   |                              |<--{0, 20, 1000}
```

Both workers see consistent state. Worker 1 proceeds, Worker 2 waits.

### Parallel Campaigns

Each campaign workspace has independent rate limit:

```
Campaign A (workspace:1)    Campaign B (workspace:2)
     |                             |
     |--rate_limit:1------------->|
     |                             |--rate_limit:2------------->|
     |                             |                            |
```

Keys are workspace-specific, so campaigns don't interfere.

### Webhook Spikes

Per-IP limits protect against spike traffic:

```
IP: 192.168.1.1              IP: 192.168.1.2
     |                             |
     |--webhook:ip:192.168.1.1--->|
     |                             |--webhook:ip:192.168.1.2--->
```

Independent limits per IP prevent one source from monopolizing capacity.

## Sliding Window Algorithm

### Data Structure

Redis sorted set with timestamp as score:

```
Key: queue:rate_limit:123

Members (score = timestamp_ms):
  1715529600123-abc123  ->  1715529600123
  1715529600134-def456  ->  1715529600134
  1715529600145-ghi789  ->  1715529600145
```

### Operations

1. **Remove expired** (before window):
   ```lua
   ZREMRANGEBYSCORE key -inf (now - window_ms)
   ```

2. **Count current** (in window):
   ```lua
   ZCARD key
   ```

3. **Add if allowed** (check-then-act):
   ```lua
   if count < limit then ZADD key now event_id end
   ```

4. **Calculate retry_after** (for rejected):
   ```lua
   oldest = ZRANGE key 0 0 WITHSCORES
   retry_after = (oldest_ts + window_ms) - now
   ```

### Window Behavior

```
Timeline (window = 60s):

t=0    t=20s  t=40s  t=60s  t=80s  t=100s
  |      |      |      |      |      |
  v      v      v      v      v      v
  [==================WINDOW==================]
        |<-- 20s -->|
             |<-- 20s -->|
                  |<-- 20s -->|
                       |<-- 20s -->|
                            |<-- 20s -->|

Entries at t=0 slide out at t=60
Entries at t=20 slide out at t=80
etc.
```

## Retry-After Calculation

When limit is exceeded, `retry_after` tells client how long to wait:

```lua
local oldest = redis.call('ZRANGE', key, 0, 0, 'WITHSCORES')
if #oldest > 0 then
    local oldest_ts = tonumber(oldest[2])
    retry_after_ms = (oldest_ts + window_ms) - now_ms
end
```

Example:
- Window: 60 seconds
- Oldest entry: 45 seconds old
- Current time: now
- Retry after: 60 - 45 = 15 seconds

This ensures client waits until oldest entry expires.

## Metrics Collection

Metrics are stored in Redis hashes for monitoring:

```lua
-- On allowed request
redis.call('HINCRBY', 'ratelimit:metrics:workspace:123', 'accepted', 1)

-- On rejected request
redis.call('HINCRBY', 'ratelimit:metrics:workspace:123', 'rejected', 1)
```

Metrics key has 1-hour TTL to prevent unbounded growth.

## Error Handling

### Redis Unavailable

Two fallback modes:

| Mode | Behavior | Use Case |
|------|----------|----------|
| `ALLOW` | Permit requests | Availability over safety |
| `DENY` | Reject requests | Safety over availability |

```python
result = await enforce_with_fallback(
    redis,
    enforce_workspace_rate_limit,
    fallback_mode=RateLimitFallbackMode.ALLOW,
    workspace_id=123,
)
```

### Connection Errors

- Log warning with error details
- Increment error counter in metrics
- Return appropriate fallback response

## Performance Characteristics

| Metric | Value |
|--------|-------|
| Script execution | O(log N) where N = entries in window |
| Memory per key | O(N) where N = events in window |
| Script size | < 1KB (small, fast execution) |
| Network latency | 1 round-trip per check |

## Key Design Decisions

### 1. Lua vs Transactions

Lua scripts are atomic at the Redis server level. Redis transactions (MULTI/EXEC) only guarantee no other commands intervene between commands, but the client can still receive intermediate results. Lua executes entirely server-side.

### 2. Sorted Sets vs Counters

Sorted sets track precise timestamps for sliding window behavior. Simple counters have fixed windows (e.g., "only 1000 per hour starting at the top of the hour") rather than sliding windows.

### 3. Event IDs Include Timestamp

Event IDs include timestamp prefix to ensure uniqueness and aid debugging:
```
1715529600123-abc123def456
```

### 4. 2x TTL on Keys

Keys expire at 2x window size to handle clock skew and ensure entries fully expire before key deletion.

## Monitoring Recommendations

Key metrics to track:

- `ratelimit:accepted` - Successful requests
- `ratelimit:rejected` - Rate-limited requests
- `ratelimit:errors` - Redis errors
- `retry_after_seconds` - Distribution of wait times

Alert thresholds:
- Rejected rate > 10% of total
- Error rate > 1%
- P99 retry_after > 10 seconds

## Testing Strategy

See `tests/queue/test_rate_limit.py` for:

1. **Unit tests**: Lua script logic, retry calculation
2. **Concurrency tests**: Simulate multiple workers
3. **Burst tests**: Traffic spikes within and exceeding limits
4. **Race condition tests**: Verify no over-limit scenarios
5. **Fallback tests**: Redis failure modes