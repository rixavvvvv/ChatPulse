from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class TriggerStatus(str, Enum):
    active = "active"
    paused = "paused"
    archived = "archived"


class TriggerSource(str, Enum):
    message_sent = "message.sent"
    message_delivered = "message.delivered"
    message_read = "message.read"
    contact_created = "contact.created"
    contact_tag_added = "contact.tag_added"
    webhook_processed = "webhook.processed"
    order_created = "order.created"
    campaign_completed = "campaign.completed"


class TriggerExecutionStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    skipped = "skipped"
    duplicate = "duplicate"


class FilterType(str, Enum):
    workspace = "workspace"
    segment = "segment"
    payload = "payload"
    metadata = "metadata"


class FilterOperator(str, Enum):
    equals = "equals"
    not_equals = "not_equals"
    contains = "contains"
    not_contains = "not_contains"
    in_list = "in_list"
    not_in_list = "not_in_list"
    greater_than = "greater_than"
    less_than = "less_than"
    exists = "exists"
    not_exists = "not_exists"


class FilterCondition(BaseModel):
    field: str = Field(..., max_length=128)
    operator: FilterOperator
    value: dict[str, Any]


class TriggerFilterCreate(BaseModel):
    filter_type: FilterType
    field: str = Field(..., max_length=128)
    operator: FilterOperator
    value: dict[str, Any]


class TriggerFilterResponse(BaseModel):
    id: int
    workflow_trigger_id: int
    filter_type: FilterType
    field: str
    operator: str
    value: dict[str, Any]
    created_at: datetime

    class Config:
        from_attributes = True


class WorkflowTriggerCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    source: TriggerSource
    filters: list[TriggerFilterCreate] = Field(default_factory=list)
    priority: int = 0


class WorkflowTriggerUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: TriggerStatus | None = None
    filters: list[TriggerFilterCreate] | None = None
    priority: int | None = None


class WorkflowTriggerResponse(BaseModel):
    id: int
    workspace_id: int
    workflow_definition_id: int
    name: str
    description: str | None
    source: TriggerSource
    status: TriggerStatus
    filters: list[dict[str, Any]]
    priority: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class WorkflowTriggerWithWorkflow(BaseModel):
    id: int
    workspace_id: int
    workflow_definition_id: int
    workflow_name: str | None = None
    name: str
    description: str | None
    source: TriggerSource
    status: TriggerStatus
    filters: list[dict[str, Any]]
    priority: int
    created_at: datetime

    class Config:
        from_attributes = True


class TriggerExecutionCreate(BaseModel):
    trigger_id: int
    event_id: int
    event_payload: dict[str, Any]


class TriggerExecutionResponse(BaseModel):
    id: int
    workspace_id: int
    workflow_trigger_id: int
    workflow_execution_id: int | None
    event_id: int | None
    dedupe_key: str
    status: TriggerExecutionStatus
    event_payload: dict[str, Any]
    error: str | None
    latency_ms: int | None
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


class TriggerStats(BaseModel):
    trigger_id: int
    workspace_id: int
    source: TriggerSource
    triggered_count: int
    matched_count: int
    executed_count: int
    failed_count: int
    skipped_duplicate_count: int
    avg_latency_ms: float | None
    last_triggered_at: datetime | None


class WorkflowTriggerStats(BaseModel):
    total_triggers: int
    active_triggers: int
    paused_triggers: int
    total_executions: int
    completed_executions: int
    failed_executions: int
    duplicate_skipped: int


class EventTriggerRequest(BaseModel):
    event_type: TriggerSource
    workspace_id: int
    event_id: int
    event_payload: dict[str, Any]
    correlation_id: str | None = None
    trace_id: str | None = None


class TriggerMatchResult(BaseModel):
    trigger_id: int
    workflow_definition_id: int
    trigger_name: str
    priority: int
    match_score: float = 1.0