# Workflow Graph Cycle Detection and Traversal Safety Architecture

## Overview

The workflow graph validation and traversal safety infrastructure prevents infinite loops, recursive execution, and worker starvation. It uses DFS/BFS algorithms to detect cycles and structural issues at workflow creation/update time, and monitors execution traversal at runtime.

## Architecture Goals

✅ **Cycle Detection**: Prevent infinite loops via graph analysis  
✅ **Structural Validation**: Detect orphan/unreachable nodes and invalid control flow  
✅ **Runtime Safety**: Enforce step and depth limits during execution  
✅ **Worker Protection**: Prevent starvation via bounded execution paths  
✅ **Observable**: Track traversal statistics and violations  
✅ **Early Detection**: Validate at workflow creation/update time

---

## Components

### 1. WorkflowGraphValidator (`app/services/workflow_graph_validator.py`)

**Purpose**: Comprehensive workflow graph validation using graph algorithms.

**Validation Checks**:

```python
# Cycle Detection (DFS Algorithm)
- Detects direct cycles (A → B → A)
- Detects indirect cycles (A → B → C → A)
- Detects self-loops (A → A)
- Returns all cyclic paths for debugging

# Structural Issues
- Missing trigger nodes (no start point)
- Unreachable nodes (BFS from triggers)
- Orphan nodes (not connected to any edge)
- Invalid join nodes (< 2 incoming edges)
- Invalid split nodes (< 2 outgoing edges)
- Invalid edges (reference non-existent nodes)

# Limits
- Max nodes per workflow (10,000)
- Max edges per workflow (50,000)
- Max traversal depth (1,000)
```

**Error Types**:

```python
class ValidationErrorType(str, Enum):
    cycle_detected = "cycle_detected"                    # Cycle found
    orphan_node = "orphan_node"                          # Not connected
    unreachable_node = "unreachable_node"                # Can't reach from trigger
    no_trigger_node = "no_trigger_node"                  # No trigger defined
    multiple_triggers = "multiple_triggers"              # Multiple triggers (warning)
    invalid_join = "invalid_join"                        # Join with < 2 inputs
    invalid_split = "invalid_split"                      # Split with < 2 outputs
    orphan_join = "orphan_join"                          # Join with no connections
    orphan_split = "orphan_split"                        # Split with no connections
    max_depth_exceeded = "max_depth_exceeded"             # Depth > limit
    invalid_edge = "invalid_edge"                        # References non-existent node
    self_loop = "self_loop"                              # Self-referencing edge
```

**Validation Result**:

```python
@dataclass
class GraphValidationResult:
    is_valid: bool                      # Overall validity
    errors: List[ValidationError]       # Detailed errors
    warnings: List[str]                 # Non-fatal warnings
    max_depth: int                      # Maximum reachable depth
    node_count: int                     # Total nodes
    edge_count: int                     # Total edges
    trigger_nodes: List[str]            # Starting nodes
    cyclic_paths: List[List[str]]       # All cycles found
```

#### DFS Cycle Detection Algorithm

```python
def detect_cycles(nodes_by_id, edges_by_source):
    """
    DFS-based cycle detection using recursion stack.
    
    Algorithm:
    1. Maintain visited set and recursion stack
    2. For each unvisited node, start DFS
    3. Mark node as visited and add to recursion stack
    4. For each neighbor:
       - If not visited, recurse
       - If in recursion stack, cycle found!
    5. Backtrack and remove from recursion stack
    
    Time Complexity: O(V + E)
    Space Complexity: O(V)
    """
    visited = set()
    rec_stack = set()
    paths = {}
    
    def dfs(node_id, path):
        visited.add(node_id)
        rec_stack.add(node_id)
        path = path + [node_id]
        paths[node_id] = path
        
        for neighbor in edges[node_id]:
            if neighbor not in visited:
                dfs(neighbor, path)
            elif neighbor in rec_stack:
                # Cycle detected!
                cycle = path[path.index(neighbor):] + [neighbor]
                yield_cycle(cycle)
        
        rec_stack.discard(node_id)
```

#### BFS Unreachable Node Detection

```python
def detect_unreachable(nodes_by_id, edges_by_source, triggers):
    """
    BFS from all trigger nodes to find reachable nodes.
    
    Algorithm:
    1. Initialize queue with all trigger nodes
    2. BFS: for each node, add unvisited neighbors
    3. Track depth during traversal
    4. Nodes not visited are unreachable
    
    Time Complexity: O(V + E)
    Space Complexity: O(V)
    """
    reachable = set()
    max_depth = 0
    
    for trigger in triggers:
        queue = [(trigger, 0)]
        visited_bfs = set()
        
        while queue:
            node_id, depth = queue.pop(0)
            max_depth = max(max_depth, depth)
            
            if node_id in visited_bfs:
                continue
            
            visited_bfs.add(node_id)
            reachable.add(node_id)
            
            for neighbor in edges[node_id]:
                if neighbor not in visited_bfs:
                    queue.append((neighbor, depth + 1))
    
    unreachable = nodes - reachable
    return unreachable, max_depth
```

---

### 2. ExecutionTraversalMonitor (`app/services/workflow_traversal_safety.py`)

**Purpose**: Runtime monitoring of execution traversal for safety violations.

**Monitoring Capabilities**:

```python
class ExecutionTraversalMonitor:
    def __init__(
        self,
        execution_id: str,
        max_steps: int = 100000,           # Max node executions
        max_depth: int = 1000,             # Max traversal depth
        warning_threshold: float = 0.8,    # Warn at 80% of limit
    ):
        self.step_count = 0                # Track execution steps
        self.current_depth = 0             # Track recursion depth
        self.max_depth_reached = 0         # Peak depth
        self.visited_nodes = set()         # Unique nodes visited
        self.visited_paths = {}            # Path frequency for loop detection
```

**Safety Enforcement**:

1. **Step Limit Enforcement**
   ```python
   def increment_step(self):
       self.step_count += 1
       if self.step_count > self.max_steps:
           raise ExecutionStepLimitExceededError(...)
   ```

2. **Depth Limit Enforcement**
   ```python
   def enter_node(self, node_id: str, current_depth: int):
       if current_depth > self.max_depth:
           raise TraversalDepthLimitExceededError(...)
   ```

3. **Loop Detection via Path Tracking**
   ```python
   def record_path(self, path: tuple):
       # Track path frequency
       if path seen twice, likely infinite loop
   ```

4. **Warning Thresholds**
   ```python
   # Warn when approaching limits
   if step_count >= (max_steps * 0.8):
       trigger_warning()
   if current_depth >= (max_depth * 0.8):
       trigger_warning()
   ```

**Statistics Collection**:

```python
@dataclass
class ExecutionTraversalStats:
    execution_id: str
    step_count: int                 # Steps executed
    max_depth_reached: int          # Peak depth
    nodes_visited: int              # Unique nodes
    node_execution_count: int       # Total node execs
    loop_detection_triggered: bool  # Loop warning
    depth_warning_at: int           # Depth warning threshold
    step_warning_at: int            # Step warning threshold
```

---

## Validation Workflow

### At Workflow Creation

```python
async def create_workflow(db, workspace_id, nodes, edges, created_by):
    # 1. Validate graph structure
    validator = WorkflowGraphValidator()
    result = validator.validate_workflow(workflow)
    
    if not result.is_valid:
        # 2. Report errors with details
        raise WorkflowValidationError(result.errors)
    
    # 3. Create workflow if valid
    workflow = WorkflowDefinition(...)
    db.add(workflow)
```

### At Workflow Update

```python
async def update_workflow(db, workflow_id, nodes, edges):
    # Re-validate entire graph on any change
    validator = WorkflowGraphValidator()
    result = validator.validate_workflow(updated_workflow)
    
    if not result.is_valid:
        raise WorkflowValidationError(result.errors)
    
    # Apply update if valid
```

### At Runtime Execution

```python
async def execute_workflow(execution, workflow):
    # 1. Create traversal monitor
    monitor = ExecutionTraversalMonitor(
        execution.execution_id,
        max_steps=100000,
        max_depth=1000,
    )
    
    try:
        while current_node_id and current_node_id in nodes:
            # 2. Check traversal limits before each node
            monitor.increment_step()
            monitor.enter_node(node_id, current_depth)
            
            # 3. Warn if approaching limits
            if monitor.is_near_step_limit():
                log_warning("Approaching step limit")
            if monitor.is_near_depth_limit():
                log_warning("Approaching depth limit")
            
            # 4. Execute node
            execute_node(...)
            
            # 5. Track path for loop detection
            monitor.record_path(current_path[-10:])
            
    except ExecutionStepLimitExceededError:
        # Cancel execution, prevent starvation
        cancel_execution(reason="step_limit_exceeded")
    except TraversalDepthLimitExceededError:
        # Cancel execution, prevent stack overflow
        cancel_execution(reason="depth_limit_exceeded")
    finally:
        # Log statistics
        stats = monitor.get_stats()
        logger.info(f"Traversal stats: {stats}")
```

---

## Cycle Detection Scenarios

### Simple Cycle

```
Workflow:  A → B → C → B
           └─────────┘

DFS Path:  visited={A,B,C}, rec_stack={A,B}
           At C → B, B in rec_stack → Cycle!
Result:    Cycle: B → C → B
```

### Self-Loop

```
Workflow:  A → B → B
                └──┘

Detection: Edge target == edge source
Result:    Self-loop detected on B
```

### Unreachable Node

```
Workflow:  A → B → C
           D → E        (D not connected)

BFS Start: A only reachable trigger
           Can reach: {A, B, C}
Result:    Unreachable: {D, E}
```

### Complex Cycle

```
Workflow:  A → B ──┐
               ↓   ↓
               C → D
               └────┘

DFS Path:  A → B → C → D → C
           At C (in rec_stack) → Cycle!
Result:    Cycle: C → D → C
```

---

## Traversal Safety Scenarios

### Step Limit Scenario

```
Execution:  max_steps = 1000, warning = 800
Traversal:  Step 1 → 200 → 400 → 600 → 800
            At 800: is_near_step_limit() = TRUE → warn
            At 1000: increment_step() succeeds
            At 1001: increment_step() throws ExecutionStepLimitExceededError
Result:     Execution cancelled
```

### Depth Limit Scenario

```
Execution:  max_depth = 100, warning = 80
Traversal:  Depth 0 → 20 → 40 → 60 → 80
            At 80: is_near_depth_limit() = TRUE → warn
            At 100: enter_node(node, 100) succeeds
            At 101: enter_node(node, 101) throws TraversalDepthLimitExceededError
Result:     Execution cancelled
```

### Loop Detection Scenario

```
Execution:  max_steps = 100000
Traversal:  Path A-B-C, then A-B-C, then A-B-C
            record_path((A,B,C)) → count=1
            record_path((A,B,C)) → count=2
            At count > 1: loop_warning_triggered = TRUE
Result:     Warning logged, can escalate to cancellation
```

---

## Configuration

### Default Settings

```python
# app/core/config.py (optional additions for graph validation)
workflow_max_nodes: int = 10000                # Max nodes per workflow
workflow_max_edges: int = 50000                # Max edges per workflow
workflow_max_traversal_depth: int = 1000       # Max reachable depth
workflow_max_execution_steps: int = 100000     # Max execution steps
```

### Validator Configuration

```python
# Strict mode (safety-first)
validator = WorkflowGraphValidator(max_depth=500)

# Permissive mode (allow deeper workflows)
validator = WorkflowGraphValidator(max_depth=2000)
```

### Traversal Monitor Configuration

```python
# Conservative (warn at 70%)
monitor = ExecutionTraversalMonitor(
    execution_id="exec1",
    max_steps=50000,
    max_depth=500,
    warning_threshold=0.7,
)

# Aggressive (warn at 90%)
monitor = ExecutionTraversalMonitor(
    execution_id="exec1",
    max_steps=100000,
    max_depth=1000,
    warning_threshold=0.9,
)
```

---

## Integration Points

### 1. Workflow Service Integration

```python
# In create_workflow / update_workflow
validator = WorkflowGraphValidator()
validation_result = validator.validate_workflow(workflow)

if not validation_result.is_valid:
    error_details = {
        "errors": [e.to_dict() for e in validation_result.errors],
        "graph_info": {
            "nodes": validation_result.node_count,
            "edges": validation_result.edge_count,
            "depth": validation_result.max_depth,
        }
    }
    raise WorkflowValidationError(error_details)
```

### 2. Workflow Engine Integration

```python
# In execute_workflow
registry = get_traversal_registry()
monitor = registry.create_monitor(execution.execution_id)

try:
    while current_node_id:
        monitor.increment_step()
        monitor.enter_node(current_node_id, current_depth)
        # Execute node...
except ExecutionStepLimitExceededError as e:
    await cancel_execution(reason="step_limit")
except TraversalDepthLimitExceededError as e:
    await cancel_execution(reason="depth_limit")
```

### 3. Monitoring/Observability

```python
# Get active execution stats
registry = get_traversal_registry()
all_stats = registry.get_stats_for_all()

for exec_id, stats in all_stats.items():
    if stats['loop_detection_triggered']:
        alert_monitoring(f"Loop detected in {exec_id}")
    if stats['step_count'] > stats['max'] * 0.9:
        alert_monitoring(f"Near step limit: {exec_id}")
```

---

## Error Handling

### Validation Errors

```python
@dataclass
class ValidationError:
    error_type: ValidationErrorType
    message: str                    # Human-readable
    node_ids: List[str]            # Affected nodes
    details: Dict                  # Extra context

# Example error
ValidationError(
    error_type=ValidationErrorType.cycle_detected,
    message="Cycle detected: A → B → C → A",
    node_ids=["A", "B", "C"],
    details={"cycle_path": ["A", "B", "C", "A"]}
)
```

### Traversal Exceptions

```python
class TraversalLimitExceededError(Exception):
    """Base traversal limit error."""

class ExecutionStepLimitExceededError(TraversalLimitExceededError):
    """Execution exceeded max steps."""

class TraversalDepthLimitExceededError(TraversalLimitExceededError):
    """Traversal exceeded max depth."""
```

### Handling in Execution

```python
try:
    # Execute workflow
except ExecutionStepLimitExceededError as e:
    # Cancel execution
    await cancellation_service.cancel_execution(
        db, execution, reason=f"step_limit: {e}"
    )
except TraversalDepthLimitExceededError as e:
    # Cancel execution
    await cancellation_service.cancel_execution(
        db, execution, reason=f"depth_limit: {e}"
    )
```

---

## Testing

### Test Cases

```python
# Cycle Detection
- test_simple_cycle()              # A → B → A
- test_self_loop()                 # A → A
- test_complex_cycle()             # A → B → C → A
- test_multiple_cycles()           # Multiple independent cycles

# Structure Validation
- test_orphan_nodes()              # Unconnected nodes
- test_unreachable_nodes()         # Not reachable from trigger
- test_invalid_split()             # Split with < 2 outputs
- test_invalid_join()              # Join with < 2 inputs
- test_missing_trigger()           # No trigger node

# Traversal Safety
- test_step_limit_enforcement()    # Steps exceed max
- test_depth_limit_enforcement()   # Depth exceeds max
- test_loop_detection()            # Repeated paths
- test_warning_thresholds()        # Warn at 80%

# Complex Scenarios
- test_deeply_nested_workflow()    # Valid deep workflow
- test_branching_with_cycles()     # Split/join with cycles
```

### Running Tests

```bash
# Run all graph validation tests
pytest tests/test_workflow_graph_validation.py -v

# Run specific test
pytest tests/test_workflow_graph_validation.py::TestWorkflowGraphValidator::test_detect_simple_cycle -v

# Run with coverage
pytest tests/test_workflow_graph_validation.py --cov=app.services.workflow_graph_validator
```

---

## Best Practices

### 1. Validate Early

```python
# ✅ Good: Validate at workflow creation
async def create_workflow(...):
    validator = WorkflowGraphValidator()
    result = validator.validate_workflow(workflow)
    if not result.is_valid:
        raise WorkflowValidationError(result.errors)

# ❌ Bad: No validation, catch errors at runtime
async def create_workflow(...):
    db.add(workflow)  # Risk!
```

### 2. Report Detailed Errors

```python
# ✅ Good: Include graph context
raise WorkflowValidationError({
    "errors": [...],
    "graph_stats": {
        "total_nodes": 50,
        "total_edges": 75,
        "max_depth": 120,
        "trigger_nodes": ["trigger1"],
    }
})

# ❌ Bad: Generic error
raise WorkflowValidationError("Invalid workflow")
```

### 3. Monitor Traversal Progress

```python
# ✅ Good: Log warnings approaching limits
if monitor.is_near_step_limit():
    logger.warning(f"Execution approaching step limit: {stats}")

# ❌ Bad: Fail suddenly at limit
if step_count > max_steps:
    crash()  # No warning
```

### 4. Set Appropriate Limits

```python
# ✅ Good: Reasonable defaults, configurable
workflow_max_depth = 1000          # Most workflows < 500
max_execution_steps = 100000       # Enough headroom

# ❌ Bad: Too aggressive
workflow_max_depth = 10            # Many valid workflows fail
max_execution_steps = 1000         # Frequent timeouts
```

---

## Performance Considerations

### Algorithm Complexity

| Operation | Time | Space | Notes |
|-----------|------|-------|-------|
| DFS Cycle Detection | O(V+E) | O(V) | Linear in graph size |
| BFS Unreachable | O(V+E) | O(V) | Linear in graph size |
| Full Validation | O(V+E) | O(V) | One-time at creation |
| Step Increment | O(1) | O(1) | Per execution step |
| Depth Check | O(1) | O(1) | Per node entry |

### Optimization Tips

1. **Cache validation results**: Valid workflows don't need re-validation
2. **Lazy unreachable detection**: Only if needed
3. **Incremental monitoring**: Don't track all paths, sample
4. **Early termination**: Stop DFS on first cycle if only checking validity

---

## Summary

The workflow graph validation and traversal safety infrastructure provides:

✅ **Compile-time cycle detection** via DFS algorithm  
✅ **Structural validation** for joins/splits/triggers  
✅ **Runtime step limits** preventing infinite loops  
✅ **Depth limit enforcement** preventing stack overflow  
✅ **Loop detection** via path frequency tracking  
✅ **Observable safety violations** with detailed error context  
✅ **Production-ready** with comprehensive test coverage
