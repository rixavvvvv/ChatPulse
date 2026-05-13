from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class WorkflowStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"


class NodeType(str, Enum):
    trigger = "trigger"
    action = "action"
    condition = "condition"
    delay = "delay"
    split = "split"
    join = "join"


class ExecutionStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    paused = "paused"


class TriggerConfig(BaseModel):
    type: str = Field(..., description="Trigger type: webhook, schedule, event")
    config: dict[str, Any] = Field(default_factory=dict)


class ActionConfig(BaseModel):
    action_type: str = Field(..., description="Action type: send_message, create_contact, update_field, etc.")
    parameters: dict[str, Any] = Field(default_factory=dict)


class ConditionConfig(BaseModel):
    expression: str = Field(..., description="CEL or similar expression")
    true_node_id: str | None = Field(None, description="Node to go on true")
    false_node_id: str | None = Field(None, description="Node to go on false")


class DelayConfig(BaseModel):
    duration_seconds: int = Field(..., description="Delay duration in seconds")


class SplitConfig(BaseModel):
    branches: list[str] = Field(..., description="List of branch node IDs")
    distribution: str = Field("all", description="Distribution: all, round_robin, random")


class JoinConfig(BaseModel):
    wait_for: list[str] = Field(..., description="Node IDs to wait for")
    mode: str = Field("all", description="Join mode: all, any")


class NodePosition(BaseModel):
    x: int = 0
    y: int = 0


class WorkflowNodeCreate(BaseModel):
    node_id: str = Field(..., max_length=64)
    node_type: NodeType
    name: str = Field(..., max_length=255)
    config: dict[str, Any] = Field(default_factory=dict)
    position: NodePosition = Field(default_factory=NodePosition)


class WorkflowNodeUpdate(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    position: NodePosition | None = None


class WorkflowNodeResponse(BaseModel):
    id: int
    workflow_definition_id: int
    node_id: str
    node_type: NodeType
    name: str
    config: dict[str, Any]
    position_x: int
    position_y: int
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowEdgeCreate(BaseModel):
    edge_id: str = Field(..., max_length=64)
    source_node_id: str = Field(..., max_length=64)
    target_node_id: str = Field(..., max_length=64)
    condition: str | None = Field(None, max_length=512)


class WorkflowEdgeResponse(BaseModel):
    id: int
    workflow_definition_id: int
    edge_id: str
    source_node_id: str
    target_node_id: str
    condition: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowDefinitionCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    nodes: list[WorkflowNodeCreate] = Field(default_factory=list)
    edges: list[WorkflowEdgeCreate] = Field(default_factory=list)


class WorkflowDefinitionUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: WorkflowStatus | None = None
    nodes: list[WorkflowNodeCreate] | None = None
    edges: list[WorkflowEdgeCreate] | None = None


class WorkflowDefinitionResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None
    status: WorkflowStatus
    definition: dict[str, Any]
    version: int
    created_by: int
    created_at: datetime
    updated_at: datetime
    nodes: list[WorkflowNodeResponse] = Field(default_factory=list)
    edges: list[WorkflowEdgeResponse] = Field(default_factory=list)

    class Config:
        from_attributes = True


class WorkflowListResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None
    status: WorkflowStatus
    version: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class TriggerWorkflowRequest(BaseModel):
    trigger_type: str = Field(..., description="webhook, schedule, manual")
    trigger_data: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionCreate(BaseModel):
    trigger_data: dict[str, Any] = Field(default_factory=dict)


class WorkflowExecutionResponse(BaseModel):
    id: int
    workspace_id: int
    workflow_definition_id: int
    execution_id: str
    status: ExecutionStatus
    trigger_data: dict[str, Any]
    context: dict[str, Any]
    current_node_id: str | None
    started_at: datetime | None
    completed_at: datetime | None
    error: str | None
    created_at: datetime

    class Config:
        from_attributes = True


class NodeExecutionResponse(BaseModel):
    id: int
    workflow_execution_id: int
    node_id: str
    node_type: NodeType
    status: ExecutionStatus
    input_data: dict[str, Any]
    output_data: dict[str, Any]
    error: str | None
    attempt_count: int
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowExecutionDetailResponse(WorkflowExecutionResponse):
    node_executions: list[NodeExecutionResponse] = Field(default_factory=list)


class ExecutionLogEntry(BaseModel):
    timestamp: datetime
    node_id: str
    node_type: NodeType
    status: ExecutionStatus
    input: dict[str, Any]
    output: dict[str, Any] | None
    error: str | None
    duration_ms: int | None


class WorkflowStats(BaseModel):
    total_executions: int
    completed: int
    failed: int
    running: int
    pending: int
    average_duration_ms: float | None