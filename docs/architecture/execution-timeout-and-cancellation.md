# Workflow Execution Timeout and Cancellation Architecture

## Overview

The workflow execution timeout and cancellation infrastructure prevents infinite delays, worker starvation, and hung workflow executions. It implements configurable timeouts at multiple levels (global, per-workflow, per-node) with graceful cancellation propagation, cleanup handlers, and recovery mechanisms.

## Architecture Goals

✅ **Prevent Worker Starvation**: Limit execution duration to prevent workers from being blocked indefinitely  
✅ **Finite Execution**: Guarantee workflow executions complete within bounded time  
✅ **Graceful Cancellation**: Propagate cancellation through workflow graph with cleanup  
✅ **Recovery Support**: Allow delayed executions to resume after timeout recovery  
✅ **Observable**: Track timeout events and metrics for monitoring  
✅ **Configurable**: Support global, workflow-level, and node-level timeout overrides

---

## Configuration

### Settings (`app/core/config.py`)

```python
workflow_execution_timeout_seconds: int = 3600           # Global default: 1 hour
workflow_node_timeout_seconds: int = 300                 # Per-node default: 5 minutes
workflow_cancellation_grace_period_seconds: int = 30     # Cancellation grace period
workflow_timeout_check_interval_seconds: int = 60        # Check interval: 1 minute
```

### Timeout Hierarchy

1. **Execution-Level Override**: `WorkflowExecution.timeout_seconds`
2. **Workflow-Level Default**: `WorkflowDefinition.timeout_seconds`
3. **Global Default**: `Settings.workflow_execution_timeout_seconds`

Node-level timeouts follow the same pattern with `Settings.workflow_node_timeout_seconds` as global default.

---

## Data Model

### WorkflowExecution Model Extensions

```python
timeout_seconds: int | None              # Execution-specific timeout (seconds)
timeout_at: datetime | None              # Computed timeout deadline (UTC)
cancelled_at: datetime | None            # Cancellation request timestamp
cancellation_reason: str | None          # "timeout", "user_request", etc.
```

**Indexes**:
- `ix_workflow_executions_timeout`: `(workspace_id, timeout_at)` for efficient deadline queries

### WorkflowDefinition Model Extensions

```python
timeout_seconds: int | None              # Per-workflow timeout override (seconds)
```

### NodeExecution Model Extensions

```python
timeout_seconds: int | None              # Per-node timeout override (seconds)
timeout_at: datetime | None              # Computed node timeout deadline (UTC)
```

**Indexes**:
- `ix_node_executions_timeout`: `(workflow_execution_id, timeout_at)` for efficient queries

---

## Services

### 1. WorkflowTimeoutService (`app/services/workflow_timeout_service.py`)

**Purpose**: Timeout deadline computation and checking.

**Key Methods**:

```python
def compute_execution_timeout_deadline(
    execution: WorkflowExecution,
    settings: Settings,
) -> datetime
    # Computes deadline based on start time + timeout seconds
    # Respects execution/workflow/global timeout hierarchy

def is_execution_timed_out(
    execution: WorkflowExecution,
    current_time: datetime | None = None,
) -> bool
    # True if execution exceeded timeout deadline
    # Returns False for terminal executions

def get_execution_time_remaining(
    execution: WorkflowExecution,
) -> timedelta | None
    # Returns remaining time before timeout

def get_timeout_percentage(
    execution: WorkflowExecution,
) -> float | None
    # 0-100% of timeout consumed (useful for warnings)

def is_approaching_timeout(
    execution: WorkflowExecution,
    warning_percentage: float = 80.0,
) -> bool
    # True if execution >= warning_percentage consumed
```

**Usage Pattern**:

```python
timeout_service = WorkflowTimeoutService(settings)

# Compute deadline when starting execution
execution.timeout_at = timeout_service.compute_execution_timeout_deadline(
    execution, settings
)

# Check timeout during execution loop
if timeout_service.is_execution_timed_out(execution):
    await cancellation_service.cancel_execution(
        db, execution, reason="timeout"
    )

# Monitor timeout progress
if timeout_service.is_approaching_timeout(execution, warning_percentage=80):
    await metrics_collector.record_timeout_warning(execution, 80.0)
```

---

### 2. WorkflowCancellationService (`app/services/workflow_cancellation_service.py`)

**Purpose**: Execution/node cancellation with propagation.

**Key Methods**:

```python
async def cancel_execution(
    session: AsyncSession,
    execution: WorkflowExecution,
    reason: str = "user_request",
    propagate: bool = True,
) -> None
    # Cancel execution and optionally propagate to child nodes
    # Updates status, sets cancelled_at, records reason
    # Propagation cascades to all running/pending nodes

async def cancel_node_execution(
    session: AsyncSession,
    node_execution: NodeExecution,
    reason: str = "execution_cancelled",
    propagate: bool = True,
) -> None
    # Cancel node and propagate downstream via edges

async def _propagate_cancellation_downstream(
    session: AsyncSession,
    execution_id: int,
    from_node_id: str,
    reason: str,
) -> None
    # Follow edges from node and cancel target nodes
    # Reason is updated to indicate parent cancellation

def is_cancellation_in_progress(
    execution: WorkflowExecution,
    grace_period_seconds: int,
) -> bool
    # True if cancelled_at is within grace period
    # Grace period allows cleanup to complete

async def force_cancel_execution(
    session: AsyncSession,
    execution: WorkflowExecution,
) -> None
    # Terminate all non-terminal nodes immediately
    # Used when grace period expires without completing
```

**Cancellation Flow**:

```
┌─────────────────────────────────────────────────────────┐
│  Timeout Detected / User Request                        │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
        ┌─────────────────┐
        │ Cancel Execution│
        │ (set status)    │
        └────────┬────────┘
                 │
         ┌───────┴─────────┐
         │ Propagate to    │
         │ child nodes     │
         ▼                 ▼
    ┌──────────┐   ┌──────────────┐
    │Cancel    │   │Cancel        │
    │running   │   │pending nodes │
    │nodes     │   │              │
    └──────────┘   └──────────────┘
         │                 │
         └────────┬────────┘
                  ▼
         ┌──────────────────┐
         │Follow edges      │
         │Cancel downstream │
         │nodes             │
         └──────────────────┘
```

---

### 3. WorkflowExecutionCleanupRegistry (`app/services/workflow_cleanup_handlers.py`)

**Purpose**: Resource cleanup handlers for cancelled/timed-out executions.

**Registered Handlers**:

1. **CeleryTaskCleanupHandler**
   - Revokes Celery tasks associated with execution
   - Uses `SIGTERM` signal for graceful termination

2. **DelayedExecutionCleanupHandler**
   - Marks delayed executions as `PENDING` (resumable)
   - Allows delayed nodes to be resumed after recovery

3. **ExecutionContextCleanupHandler**
   - Clears temporary execution context
   - Optionally clears node output data to free memory

**Usage**:

```python
registry = get_cleanup_registry()

# Register handlers during app initialization
registry.register("celery_tasks", CeleryTaskCleanupHandler(celery_app))
registry.register("delayed_execution", DelayedExecutionCleanupHandler())
registry.register("execution_context", ExecutionContextCleanupHandler())

# Run cleanup when cancelling
cleanup_results = await registry.cleanup_execution(
    session,
    execution,
    handlers=["celery_tasks", "delayed_execution"],
    make_resumable=True,
)
```

---

### 4. WorkflowTimeoutMetricsCollector (`app/services/workflow_timeout_metrics.py`)

**Purpose**: Track timeout events and aggregate metrics.

**Event Types**:

- `execution_timeout`: Execution exceeded timeout
- `execution_timeout_warning`: Execution approaching timeout (>80%)
- `node_timeout`: Node exceeded timeout
- `node_timeout_warning`: Node approaching timeout
- `cancellation_initiated`: Cancellation started
- `cancellation_completed`: Cancellation finished
- `cancellation_grace_period_exceeded`: Grace period expired

**Metrics Tracked**:

```python
@dataclass
class TimeoutMetrics:
    total_executions: int
    total_timeouts: int
    total_cancellations: int
    node_timeouts: int
    recovered_from_timeout: int
    avg_timeout_percentage: float
```

**Usage**:

```python
metrics = get_metrics_collector()

# Record events
await metrics.record_execution_timeout(session, execution, 95.5)
await metrics.record_timeout_warning(execution, 80.0)
await metrics.record_cancellation(execution, "timeout")

# Get metrics
workspace_metrics = metrics.get_metrics(workspace_id)
event_history = event_bus.get_event_history(workspace_id)
```

---

### 5. WorkflowTraversalEngine Updates (`app/services/workflow_engine.py`)

**Integration Points**:

1. **Initialization**: Engine receives `Settings` for timeout config
   ```python
   engine = WorkflowTraversalEngine(db, settings)
   engine.timeout_service = WorkflowTimeoutService(settings)
   engine.cancellation_service = WorkflowCancellationService()
   ```

2. **Execution Startup**: Compute timeout deadline
   ```python
   execution.timeout_at = timeout_service.compute_execution_timeout_deadline(
       execution, settings
   )
   ```

3. **Execution Loop**: Check timeout before each node
   ```python
   if timeout_service.is_execution_timed_out(execution):
       await cancellation_service.cancel_execution(...)
       break
   ```

4. **Node Execution**: Protect with asyncio timeout
   ```python
   effective_timeout = min(
       node_timeout_seconds,
       execution_remaining_seconds,
   )
   result = await asyncio.wait_for(
       handler(node, execution),
       timeout=effective_timeout,
   )
   ```

5. **Delay Nodes**: Handle interruption for resumption
   ```python
   # delay handler catches asyncio.CancelledError
   # to allow resumption via delayed execution recovery
   try:
       await asyncio.sleep(duration)
   except asyncio.CancelledError:
       # Can be resumed later
       raise
   ```

---

### 6. DelayedExecutionRecoveryService (`app/services/delayed_execution_recovery_service.py`)

**Purpose**: Resume delayed executions after timeout recovery.

**Key Methods**:

```python
async def find_resumable_delayed_executions(
    session: AsyncSession,
    workspace_id: int,
    execution_id: int | None = None,
    limit: int = 100,
) -> list[DelayedExecution]
    # Find SCHEDULED/PENDING delayed executions

async def mark_resumable_after_timeout(
    session: AsyncSession,
    execution: WorkflowExecution,
) -> int
    # Mark all delayed nodes in execution as PENDING
    # Returns count of marked executions

async def resume_delayed_execution(
    session: AsyncSession,
    delayed_execution: DelayedExecution,
    parent_execution: WorkflowExecution,
) -> bool
    # Resume execution within parent context
    # Respects parent execution status

async def get_delayed_execution_stats(
    session: AsyncSession,
    workspace_id: int,
) -> dict
    # Get statistics:
    # - total, scheduled, pending, running, etc.
    # - resumable count, overdue count
```

**Recovery Flow**:

```
┌──────────────────────────────────────────────┐
│  Timeout Occurs in Execution                 │
└────────────────┬─────────────────────────────┘
                 │
                 ▼
    ┌────────────────────────────┐
    │ Trigger Cancellation        │
    │ (propagate to nodes)        │
    └────────┬───────────────────┘
             │
             ▼
    ┌─────────────────────────────────┐
    │ Run Cleanup Handlers             │
    │ (mark delayed nodes PENDING)     │
    └────────┬────────────────────────┘
             │
             ▼
    ┌──────────────────────────────────┐
    │ Execution Status → CANCELLED     │
    └────────┬─────────────────────────┘
             │
      ┌──────┴──────┐
      ▼             ▼
  ┌────────┐  ┌──────────────────────┐
  │Delayed │  │Recovery Process:     │
  │Nodes   │  │ - Resume delayed     │
  │saved   │  │ - Mark as PENDING    │
  │        │  │ - Restart from delay │
  └────────┘  └──────────────────────┘
```

---

## Execution Timeout States

### Execution Status Transitions

```
PENDING → RUNNING → (checking timeout)
           ├─→ TIMEOUT DETECTED ─→ CANCELLED
           ├─→ COMPLETED
           └─→ FAILED
```

### Cancellation States

- `cancelled_at is None`: No cancellation
- `cancelled_at < now`: Cancellation grace period active
- `cancelled_at + grace_period <= now`: Force cancel ready

---

## Timeout Workflow

### Typical Timeout Scenario

```
T=0s    Execution starts with timeout_at = T+3600s
T=100s  Node 1 executes (timeout_at = T+300s)
T=250s  Node 2 executes
T=3500s Execution loop detects timeout
        - is_execution_timed_out(execution) = TRUE
        - cancel_execution(execution, reason="timeout")
        - Mark all delayed nodes as PENDING
T=3530s Grace period expires, force cancel any remaining nodes
T=3540s Cleanup completes, execution marked CANCELLED
```

### Recovery Scenario

```
T=0s    Workflow starts with delay node scheduled for T+7200s
T=3600s Execution times out
        - Delay node marked PENDING in delayed_executions table
        - Execution CANCELLED
T=3601s Recovery process starts
        - find_resumable_delayed_executions(workspace_id, execution_id)
        - Resume delay node from PENDING status
        - Continue workflow execution from delay point
```

---

## Timeout Propagation

### Cancellation Propagation Rules

1. **Immediate Parent Node**: Marks as CANCELLED
2. **Downstream Nodes**: Followed via workflow edges
3. **Reason Accumulation**: "timeout" → "timeout (parent cancelled)"
4. **Terminal Nodes**: Not affected if already complete/failed

### Example Propagation

```
Workflow DAG:
┌──────┐
│Start │
└───┬──┘
    │
    ▼
┌──────────┐
│Delay(2h) │ ◄─── TIMEOUT HERE
└───┬──────┘
    │
    ├──► ┌────────┐
    │    │Action1 │
    │    └────────┘
    │
    └──► ┌────────┐
         │Action2 │
         └────────┘

Cancellation Propagation:
1. Delay node → CANCELLED (reason: timeout)
2. Action1 → CANCELLED (reason: timeout (parent cancelled))
3. Action2 → CANCELLED (reason: timeout (parent cancelled))
```

---

## Delayed Execution Resumption

### Prerequisites for Resumption

1. **Status**: Delayed execution must be PENDING or SCHEDULED
2. **Parent State**: Parent execution must not be terminal
3. **Deadline**: Can be resumed if deadline not yet passed
4. **Resumability**: Node handler must support cancellation (e.g., delay nodes)

### Resumption Process

```python
# 1. Find resumable delayed executions
resumable = await recovery_service.find_resumable_delayed_executions(
    session, workspace_id, execution_id
)

# 2. For each delayed execution
for delayed_exec in resumable:
    # 3. Resume within parent execution context
    success = await recovery_service.resume_delayed_execution(
        session, delayed_exec, parent_execution
    )
    
    if success:
        # 4. Workflow engine picks it up in next cycle
        # 5. Continue from delay node
```

---

## Metrics and Observability

### Key Metrics

- **Execution Timeouts**: Count of executions that timed out
- **Node Timeouts**: Count of nodes that timed out
- **Cancellations**: Count of cancellations (timeout + user)
- **Timeout Percentage**: Distribution of timeout consumption
- **Recovery Rate**: Executions recovered after timeout
- **Grace Period Exceeded**: Cancellations requiring force-cancel

### Event Stream

```python
event_bus.subscribe(
    TimeoutEventType.execution_timeout,
    lambda event: logger.warning(f"Execution {event.execution_id} timed out"),
)

event_bus.subscribe(
    TimeoutEventType.execution_timeout_warning,
    lambda event: alert_monitoring(f"Execution approaching timeout"),
)
```

---

## Best Practices

### 1. Set Appropriate Timeouts

```python
# Global (production)
workflow_execution_timeout_seconds = 3600  # 1 hour

# Per-workflow (if needed)
workflow.timeout_seconds = 7200  # 2 hours for long-running

# Per-node (for external API calls)
node.config['timeout_seconds'] = 30  # 30s for network calls
```

### 2. Handle Delayed Nodes

```python
# Delay nodes are automatically resumable
# Ensure delay configuration is idempotent

# After recovery, delayed nodes are marked PENDING
# They resume from the delay point (not from start)
```

### 3. Monitor Timeout Events

```python
# Subscribe to warnings (>80% timeout)
metrics.subscribe(
    TimeoutEventType.execution_timeout_warning,
    send_alert_to_slack,
)

# Track cancellation reasons
for event in event_history:
    if event.event_type == TimeoutEventType.cancellation_initiated:
        log_cancellation_reason(event.reason)
```

### 4. Graceful Cleanup

```python
# Cleanup handlers run in order:
# 1. Revoke Celery tasks
# 2. Mark delayed executions resumable
# 3. Clear execution context

# Custom handlers can be registered:
registry.register("custom", CustomCleanupHandler())
```

---

## Configuration Examples

### Development Configuration

```bash
WORKFLOW_EXECUTION_TIMEOUT_SECONDS=600          # 10 minutes
WORKFLOW_NODE_TIMEOUT_SECONDS=60                # 1 minute
WORKFLOW_CANCELLATION_GRACE_PERIOD_SECONDS=10   # 10 seconds
WORKFLOW_TIMEOUT_CHECK_INTERVAL_SECONDS=5       # 5 seconds (frequent check)
```

### Production Configuration

```bash
WORKFLOW_EXECUTION_TIMEOUT_SECONDS=3600         # 1 hour
WORKFLOW_NODE_TIMEOUT_SECONDS=300               # 5 minutes
WORKFLOW_CANCELLATION_GRACE_PERIOD_SECONDS=30   # 30 seconds
WORKFLOW_TIMEOUT_CHECK_INTERVAL_SECONDS=60      # 1 minute
```

### Long-Running Workflows

```bash
WORKFLOW_EXECUTION_TIMEOUT_SECONDS=28800        # 8 hours
WORKFLOW_NODE_TIMEOUT_SECONDS=1800              # 30 minutes
```

---

## Testing

### Timeout Simulation

```python
# Test timeout with short deadline
execution.timeout_at = datetime.now(timezone.utc) + timedelta(seconds=1)

# Simulate slow node
async def slow_handler(node, execution):
    await asyncio.sleep(10)

# Should timeout
with pytest.raises(asyncio.TimeoutError):
    await engine.execute_workflow(execution, workflow)
```

### Cancellation Propagation Test

```python
# Verify cascading cancellation
execution = await engine.execute_workflow(execution, workflow)
assert execution.status == ExecutionStatus.cancelled

# Check all nodes cancelled
for node_exec in execution.node_executions:
    assert node_exec.status == ExecutionStatus.cancelled
```

### Recovery Test

```python
# Test delayed execution resumption
recovery_service = DelayedExecutionRecoveryService()
resumable = await recovery_service.find_resumable_delayed_executions(
    session, workspace_id, execution_id
)
assert len(resumable) > 0

# Resume and verify
success = await recovery_service.resume_delayed_execution(
    session, resumable[0], execution
)
assert success is True
```

---

## Summary

The timeout and cancellation infrastructure provides:

✅ **Multi-level timeout configuration** (global, workflow, node)  
✅ **Graceful cancellation propagation** through workflow graph  
✅ **Resource cleanup** via pluggable handlers  
✅ **Delayed execution resumption** after timeout recovery  
✅ **Observable metrics and events** for monitoring  
✅ **Prevention of worker starvation** and hung executions
