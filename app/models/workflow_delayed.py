from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


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


class BusinessHoursConfig(Base):
    """Stores business hours configuration for timezone-aware scheduling."""

    __tablename__ = "business_hours_config"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    timezone: Mapped[str] = mapped_column(String(64), nullable=False, default="UTC")
    day_of_week: Mapped[int] = mapped_column(Integer, nullable=False)
    start_time: Mapped[str] = mapped_column(String(8), nullable=False)
    end_time: Mapped[str] = mapped_column(String(8), nullable=False)
    is_active: Mapped[bool] = mapped_column(Integer, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_business_hours_workspace_day", "workspace_id", "day_of_week"),
    )


class DelayedExecution(Base):
    """Stores delayed workflow execution schedules."""

    __tablename__ = "delayed_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    workflow_definition_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_definitions.id"),
        nullable=False,
        index=True,
    )
    workflow_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_executions.id"),
        nullable=True,
        index=True,
    )
    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    delay_type: Mapped[DelayType] = mapped_column(
        SqlEnum(DelayType, name="delay_type"),
        nullable=False,
    )
    delay_config: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )

    scheduled_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    window_start: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    window_end: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    status: Mapped[DelayedExecutionStatus] = mapped_column(
        SqlEnum(DelayedExecutionStatus, name="delayed_execution_status"),
        nullable=False,
        default=DelayedExecutionStatus.scheduled,
    )

    context: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    trigger_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    idempotency_key: Mapped[str] = mapped_column(String(256), nullable=True, index=True)

    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_delayed_executions_status_scheduled", "status", "scheduled_at"),
        Index("ix_delayed_executions_workflow_status", "workflow_definition_id", "status"),
    )


class ExecutionLease(Base):
    """Manages execution leases for delayed tasks to prevent duplicate execution."""

    __tablename__ = "execution_leases"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    delayed_execution_id: Mapped[int] = mapped_column(
        ForeignKey("delayed_executions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    lease_key: Mapped[str] = mapped_column(String(256), nullable=False, unique=True, index=True)
    worker_id: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[LeaseStatus] = mapped_column(
        SqlEnum(LeaseStatus, name="lease_status"),
        nullable=False,
        default=LeaseStatus.available,
    )
    leased_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    released_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index("ix_execution_lease_delayed", "delayed_execution_id", "status"),
    )


class DelayedExecutionMetrics(Base):
    """Aggregated metrics for delayed execution monitoring."""

    __tablename__ = "delayed_execution_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    delay_type: Mapped[str] = mapped_column(String(32), nullable=False)

    scheduled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    expired_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    avg_delay_seconds: Mapped[float | None] = mapped_column(Integer, nullable=True)
    max_delay_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_delayed_metrics_period", "workspace_id", "period_start"),
    )