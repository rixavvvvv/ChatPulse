# Tenant Isolation / Workspace Security Architecture

## Overview

ChatPulse implements workspace-based tenant isolation to ensure that data and resources from one workspace cannot be accessed by users or processes from another workspace. This document outlines the security architecture, patterns, and enforcement mechanisms.

## Core Principles

### 1. Workspace as Security Boundary
- Every resource (workflow, trigger, conversation, campaign, etc.) belongs to exactly one workspace
- All operations must specify the target workspace
- Resources cannot be accessed across workspace boundaries

### 2. Defense in Depth
Multiple layers of protection:
- **Application Layer**: Workspace validation in service methods
- **Database Layer**: Foreign key constraints and indexes
- **API Layer**: Workspace ID in all request parameters
- **Queue Layer**: Workspace ID passed through async tasks

### 3. Fail-Secure Default
- Invalid or missing workspace IDs are rejected, not defaulted
- Unknown workspaces result in access denial, not unauthenticated access

## Architecture Components

### Workspace Security Module (`workspace_security.py`)

```
┌─────────────────────────────────────────────────────────────────┐
│                  Workspace Security Module                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────┐    ┌──────────────────┐                   │
│  │ require_workspace│    │ validate_workspace│                   │
│  │ _id()            │    │ _ownership()      │                   │
│  │ - Type check     │    │ - Fetch resource  │                   │
│  │ - Positive int   │    │ - Compare IDs     │                   │
│  │ - Not zero       │    │ - Deny if diff    │                   │
│  └──────────────────┘    └──────────────────┘                   │
│           │                      │                              │
│           └──────────┬───────────┘                              │
│                      ▼                                          │
│  ┌──────────────────────────────────────────┐                   │
│  │       WorkspaceContext (Context Manager) │                   │
│  │  - Scopes all ops to a workspace         │                   │
│  │  - Validates before each operation        │                   │
│  └──────────────────────────────────────────┘                   │
│                                                                  │
│  Validators:                                                    │
│  - validate_trigger_ownership()                                 │
│  - validate_workflow_ownership()                                │
│  - validate_delayed_execution_ownership()                       │
│  - validate_conversation_ownership()                           │
│  - validate_campaign_ownership()                               │
│  - validate_automation_ownership()                            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## Validation Patterns

### 1. Direct Service Validation

```python
# In service methods - always include workspace filter
async def get_trigger_by_id(
    db: AsyncSession,
    trigger_id: int,
    workspace_id: int,  # Always required
) -> WorkflowTrigger | None:
    stmt = select(WorkflowTrigger).where(
        and_(
            WorkflowTrigger.id == trigger_id,
            WorkflowTrigger.workspace_id == workspace_id,  # Enforce isolation
        )
    )
```

### 2. Ownership Validation (For Critical Operations)

```python
# For sensitive operations, validate ownership explicitly
async def execute_workflow_task(
    trigger_id: int,
    workspace_id: int,  # Required parameter
    ...
):
    # Validate workspace_id is valid
    require_workspace_id(workspace_id, "execute_workflow_task")

    # Validate trigger belongs to this workspace
    try:
        trigger = await validate_trigger_ownership(db, trigger_id, workspace_id)
    except WorkspaceAccessDenied:
        return {"status": "access_denied"}

    # Validate workflow belongs to this workspace
    workflow = await validate_workflow_ownership(db, trigger.workflow_definition_id, workspace_id)
```

### 3. Context Manager Pattern

```python
# For operations requiring multiple resource validations
async with WorkspaceContext(db, workspace_id) as ctx:
    trigger = await ctx.validate_trigger(trigger_id)
    workflow = await ctx.validate_workflow(workflow_id)
    # All operations now validated
```

## Threat Model

### Threat 1: Cross-Workspace Trigger Execution
**Scenario**: User in Workspace A triggers workflow belonging to Workspace B

**Mitigation**:
1. Trigger task requires `workspace_id` parameter
2. `validate_trigger_ownership()` checks trigger.workspace_id == requested_workspace_id
3. If mismatch, returns access_denied status

**Code Path**:
```
ProcessEventTask (passes workspace_id)
  └─> execute_workflow.s(trigger_id, event_id, workspace_id=5)
       └─> validate_trigger_ownership(db, trigger_id=123, workspace_id=5)
            └─> Raises WorkspaceAccessDenied if trigger.workspace_id != 5
```

### Threat 2: Workflow Definition Access
**Scenario**: User accesses workflow definition from another workspace

**Mitigation**:
1. All workflow lookups require workspace_id in query filter
2. Additional ownership validation for execute operations

**Code Path**:
```
WorkflowExecutionTask
  └─> validate_workflow_ownership(db, workflow_id, workspace_id)
       └─> Raises WorkspaceAccessDenied if workflow.workspace_id != workspace_id
```

### Threat 3: Conversation Data Leakage
**Scenario**: Agent in Workspace A reads conversation from Workspace B

**Mitigation**:
1. List queries always include workspace_id filter
2. Get-by-id validates ownership
3. WebSocket events filtered by workspace

**Code Path**:
```
GET /conversations/{id}
  └─> get_conversation_by_id(db, id, workspace_id=5)
       └─> Query: WHERE id=? AND workspace_id=5
```

### Threat 4: Queue Task Parameter Manipulation
**Scenario**: Malicious actor modifies Celery task parameters to access cross-workspace data

**Mitigation**:
1. Tasks validate workspace_id before processing
2. Redis locks include workspace_id in key
3. Idempotency keys include workspace context

**Code Path**:
```
Celery Task (trigger.execute_workflow)
  └─> require_workspace_id(workspace_id)  # Validates parameter
       └─> validate_trigger_ownership()  # Validates ownership
            └─> Process only if workspace matches
```

## Anti-Patterns (Must Avoid)

### ❌ Hardcoded Workspace ID
```python
# BAD - bypasses isolation
trigger = await get_trigger_by_id(db, trigger_id, 0)
```

### ❌ Missing Workspace Filter
```python
# BAD - allows cross-workspace access
trigger = await db.get(WorkflowTrigger, trigger_id)
```

### ❌ Optional Workspace ID
```python
# BAD - allows bypass
async def get_trigger(trigger_id: int, workspace_id: int | None = None):
```

### ❌ Trusting Caller's Workspace
```python
# BAD - caller could lie
async def do_something(trigger, workspace_id_from_caller):
    # Direct access without validation
    process(trigger)
```

## Audit & Monitoring

### Access Violation Logging
```python
logger.warning(
    "Workspace isolation violation: %s %d owned by workspace %d, "
    "access attempted by workspace %d",
    resource_name, resource_id, actual_workspace, requested_workspace
)
```

### Metrics to Track
- `workspace_access_denied_count` - Total access violations
- `workspace_validation_errors` - Invalid workspace IDs
- `cross_workspace_attempts` - Attempted cross-workspace accesses

## Testing Strategy

### Unit Tests
- `require_workspace_id()` - Valid/invalid IDs
- `validate_*_ownership()` - Success/failure cases
- `WorkspaceContext` - Context manager behavior

### Integration Tests
- Task execution with workspace validation
- API endpoints with workspace filtering
- Service methods with ownership checks

### Security Tests
- Malicious payload attempts
- Parameter manipulation
- Race conditions in validation

## Service Coverage

| Service | Workspace Validation | Notes |
|---------|---------------------|-------|
| `trigger_service` | ✓ Query filter | Primary entry point |
| `workflow_service` | ✓ Query filter + ownership | Execution path |
| `delayed_execution_service` | ✓ Query filter | Scheduling path |
| `conversation_service` | ✓ Query filter | Inbox operations |
| `campaign_service` | ✓ Query filter | Bulk operations |
| `ecommerce_automation_service` | ✓ Query filter | Automation path |

## Future Enhancements

1. **Row-Level Security**: Database-level workspace filtering
2. **Audit Log**: Complete access audit trail
3. **Workspace Groups**: Cross-workspace collaboration with explicit sharing
4. **Rate Limiting Per Workspace**: Isolate rate limit counters by workspace