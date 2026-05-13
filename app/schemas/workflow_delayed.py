from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class DelayType(str, Enum):
    fixed = "fixed"
    relative = "relative"
    wait_until = "wait_until"
    business_hours = "business_hours"


class DelayedExecutionStatus(str, Enum):
    scheduled = "scheduled"
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    cancelled = "cancelled"
    expired = "expired"


class LeaseStatus(str, Enum):
    available = "available"
    leased = "leased"
    released = "released"
    expired = "expired"


class FixedDelayConfig(BaseModel):
    duration_seconds: int = Field(..., description="Fixed delay in seconds")


class RelativeDelayConfig(BaseModel):
    field: str = Field(..., description="Field to calculate relative delay from")
    offset_seconds: int = Field(..., description="Seconds to add to the field value")
    fallback_seconds: int = Field(0, description="Fallback if field not present")


class WaitUntilConfig(BaseModel):
    timestamp_field: str = Field(..., description="Field containing the timestamp")
    timezone: str = Field("UTC", description="Timezone for timestamp")
    allow_past: bool = Field(True, description="Allow execution if timestamp is in past")


class BusinessHoursConfigSchema(BaseModel):
    timezone: str = Field("UTC", description="IANA timezone")
    business_hours: list[dict[str, Any]] = Field(
        default_factory=list,
        description="List of business hours: {day_of_week: 0-6, start_time: 'HH:MM', end_time: 'HH:MM'}"
    )


class DelayConfig(BaseModel):
    delay_type: DelayType
    config: dict[str, Any]


class DelayedExecutionCreate(BaseModel):
    workflow_definition_id: int
    delay_config: DelayConfig
    context: dict[str, Any] = Field(default_factory=dict)
    trigger_data: dict[str, Any] = Field(default_factory=dict)
    max_retries: int = 3
    idempotency_key: str | None = None


class DelayedExecutionUpdate(BaseModel):
    status: DelayedExecutionStatus | None = None
    scheduled_at: datetime | None = None
    context: dict[str, Any] | None = None
    max_retries: int | None = None


class DelayedExecutionResponse(BaseModel):
    id: int
    workspace_id: int
    workflow_definition_id: int
    workflow_execution_id: int | None
    execution_id: str
    delay_type: DelayType
    delay_config: dict[str, Any]
    scheduled_at: datetime
    window_start: datetime | None
    window_end: datetime | None
    status: DelayedExecutionStatus
    context: dict[str, Any]
    trigger_data: dict[str, Any]
    idempotency_key: str | None
    retry_count: int
    max_retries: int
    error: str | None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    completed_at: datetime | None

    class Config:
        from_attributes = True


class DelayedExecutionListResponse(BaseModel):
    id: int
    workspace_id: int
    workflow_definition_id: int
    execution_id: str
    delay_type: DelayType
    scheduled_at: datetime
    status: DelayedExecutionStatus
    retry_count: int
    created_at: datetime

    class Config:
        from_attributes = True


class LeaseResponse(BaseModel):
    id: int
    delayed_execution_id: int
    lease_key: str
    worker_id: str
    status: LeaseStatus
    leased_at: datetime
    expires_at: datetime

    class Config:
        from_attributes = True


class BusinessHoursCreate(BaseModel):
    timezone: str = "UTC"
    day_of_week: int = Field(..., ge=0, le=6)
    start_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    end_time: str = Field(..., pattern=r"^\d{2}:\d{2}$")
    is_active: bool = True


class BusinessHoursResponse(BaseModel):
    id: int
    workspace_id: int
    timezone: str
    day_of_week: int
    start_time: str
    end_time: str
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class DelayedExecutionStats(BaseModel):
    total_scheduled: int
    completed: int
    failed: int
    running: int
    pending: int
    expired: int
    avg_delay_seconds: float | None


class DelayedMetricsResponse(BaseModel):
    workspace_id: int
    delay_type: str
    scheduled_count: int
    completed_count: int
    failed_count: int
    avg_delay_seconds: float | None
    period_start: datetime
    period_end: datetime