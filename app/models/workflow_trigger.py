from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


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


class WorkflowTrigger(Base):
    __tablename__ = "workflow_triggers"

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
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[TriggerSource] = mapped_column(
        SqlEnum(TriggerSource, name="trigger_source"),
        nullable=False,
        index=True,
    )
    status: Mapped[TriggerStatus] = mapped_column(
        SqlEnum(TriggerStatus, name="trigger_status"),
        nullable=False,
        default=TriggerStatus.active,
    )
    filters: Mapped[list[dict]] = mapped_column(
        JSON,
        nullable=False,
        default=list,
    )
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_by: Mapped[int] = mapped_column(
        ForeignKey("users.id"),
        nullable=False,
    )
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

    executions: Mapped[list["TriggerExecution"]] = relationship(
        back_populates="trigger",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_workflow_triggers_source_status", "source", "status"),
        Index("ix_workflow_triggers_workflow_source", "workflow_definition_id", "source"),
    )


class TriggerFilter(Base):
    __tablename__ = "trigger_filters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workflow_trigger_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_triggers.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    filter_type: Mapped[FilterType] = mapped_column(
        SqlEnum(FilterType, name="filter_type"),
        nullable=False,
    )
    field: Mapped[str] = mapped_column(String(128), nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    value: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_trigger_filters_trigger", "workflow_trigger_id", "filter_type"),
    )


class TriggerExecution(Base):
    __tablename__ = "trigger_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    workflow_trigger_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_triggers.id"),
        nullable=False,
        index=True,
    )
    workflow_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("workflow_executions.id"),
        nullable=True,
        index=True,
    )
    event_id: Mapped[int | None] = mapped_column(
        ForeignKey("domain_events.id"),
        nullable=True,
        index=True,
    )
    dedupe_key: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    status: Mapped[TriggerExecutionStatus] = mapped_column(
        SqlEnum(TriggerExecutionStatus, name="trigger_execution_status"),
        nullable=False,
        default=TriggerExecutionStatus.pending,
    )
    event_payload: Mapped[dict] = mapped_column(
        JSON,
        nullable=False,
        default=dict,
    )
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    trigger: Mapped["WorkflowTrigger"] = relationship(back_populates="executions")

    __table_args__ = (
        Index("ix_trigger_executions_dedupe", "workflow_trigger_id", "dedupe_key", unique=True),
        Index("ix_trigger_executions_status", "workspace_id", "status"),
    )


class TriggerMetrics(Base):
    __tablename__ = "trigger_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    trigger_id: Mapped[int] = mapped_column(
        ForeignKey("workflow_triggers.id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(128), nullable=False)
    triggered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    matched_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    executed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    skipped_duplicate_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    avg_latency_ms: Mapped[float | None] = mapped_column(Integer, nullable=True)
    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_trigger_metrics_period", "workspace_id", "trigger_id", "period_start"),
    )