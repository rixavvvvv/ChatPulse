from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, JSON, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base


class EcommerceAutomationType(str, Enum):
    abandoned_cart_recovery = "abandoned_cart_recovery"
    order_confirmation = "order_confirmation"
    shipment_updates = "shipment_updates"
    delivered_notifications = "delivered_notifications"
    cod_verification = "cod_verification"
    post_purchase_followup = "post_purchase_followup"
    review_request = "review_request"
    custom = "custom"


class AutomationTriggerType(str, Enum):
    cart_abandoned = "cart_abandoned"
    order_created = "order_created"
    order_cancelled = "order_cancelled"
    shipment_created = "shipment_created"
    shipment_delivered = "shipment_delivered"
    order_fulfilled = "order_fulfilled"
    payment_received = "payment_received"
    cod_pending = "cod_pending"
    manual = "manual"


class EcommerceAutomationStatus(str, Enum):
    draft = "draft"
    active = "active"
    paused = "paused"
    archived = "archived"


class ExecutionStatus(str, Enum):
    pending = "pending"
    scheduled = "scheduled"
    sent = "sent"
    delivered = "delivered"
    failed = "failed"
    cancelled = "cancelled"


class AttributionModel(str, Enum):
    first_touch = "first_touch"
    last_touch = "last_touch"
    linear = "linear"
    time_decay = "time_decay"


class EcommerceAutomation(Base):
    __tablename__ = "ecommerce_automations"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    automation_type: Mapped[EcommerceAutomationType] = mapped_column(
        SqlEnum(EcommerceAutomationType, name="ecommerce_automation_type"),
        nullable=False,
    )
    trigger_type: Mapped[AutomationTriggerType] = mapped_column(
        SqlEnum(AutomationTriggerType, name="automation_trigger_type"),
        nullable=False,
    )
    status: Mapped[EcommerceAutomationStatus] = mapped_column(
        SqlEnum(EcommerceAutomationStatus, name="ecommerce_automation_status"),
        nullable=False,
        default=EcommerceAutomationStatus.draft,
    )

    trigger_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    action_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    delay_seconds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delay_type: Mapped[str] = mapped_column(String(32), nullable=True)

    segment_id: Mapped[int | None] = mapped_column(
        ForeignKey("segments.id"),
        nullable=True,
        index=True,
    )

    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("templates.id"),
        nullable=True,
    )

    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False, default=3)

    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
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

    executions: Mapped[list["EcommerceAutomationExecution"]] = relationship(
        back_populates="automation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        Index("ix_ecommerce_automation_type_status", "automation_type", "status"),
        Index("ix_ecommerce_automation_trigger", "trigger_type", "status"),
    )


class EcommerceAutomationExecution(Base):
    __tablename__ = "ecommerce_automation_executions"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("ecommerce_automations.id"),
        nullable=False,
        index=True,
    )
    order_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    cart_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
    )

    execution_id: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)

    # Idempotency key for duplicate prevention - unique per automation
    idempotency_key: Mapped[str | None] = mapped_column(String(256), nullable=True, index=True)

    status: Mapped[ExecutionStatus] = mapped_column(
        SqlEnum(ExecutionStatus, name="ecommerce_execution_status"),
        nullable=False,
        default=ExecutionStatus.pending,
    )

    trigger_data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    message_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)

    delayed_execution_id: Mapped[int | None] = mapped_column(
        ForeignKey("delayed_executions.id"),
        nullable=True,
        index=True,
    )

    message_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

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

    automation: Mapped["EcommerceAutomation"] = relationship(back_populates="executions")

    __table_args__ = (
        Index("ix_automation_execution_status", "automation_id", "status"),
        Index("ix_automation_execution_order", "order_id", "status"),
        Index("ix_automation_execution_idempotency", "automation_id", "idempotency_key", unique=True),
        # Partial unique constraint: prevents duplicate pending/scheduled executions per automation
        # Use idempotency_key for fine-grained control
    )


class EcommerceAttribution(Base):
    __tablename__ = "ecommerce_attribution"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    contact_id: Mapped[int] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=False,
        index=True,
    )

    order_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cart_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

    attribution_model: Mapped[AttributionModel] = mapped_column(
        SqlEnum(AttributionModel, name="attribution_model"),
        nullable=False,
    )

    touchpoints: Mapped[list[dict]] = mapped_column(JSON, nullable=False, default=list)

    revenue: Mapped[float] = mapped_column(Integer, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="USD")

    converted: Mapped[bool] = mapped_column(Integer, nullable=False, default=False)
    conversion_timestamp: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    first_touch_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    last_touch_id: Mapped[str | None] = mapped_column(String(128), nullable=True)

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

    __table_args__ = (
        Index("ix_attribution_contact_order", "contact_id", "order_id", unique=True),
        Index("ix_attribution_converted", "workspace_id", "converted"),
    )


class EcommerceAutomationMetrics(Base):
    __tablename__ = "ecommerce_automation_metrics"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    automation_id: Mapped[int] = mapped_column(
        ForeignKey("ecommerce_automations.id"),
        nullable=False,
        index=True,
    )
    automation_type: Mapped[str] = mapped_column(String(64), nullable=False)

    scheduled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    delivered_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cancelled_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    conversion_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    revenue: Mapped[float] = mapped_column(Integer, nullable=False, default=0)

    avg_time_to_send_seconds: Mapped[float | None] = mapped_column(Integer, nullable=True)
    open_rate: Mapped[float | None] = mapped_column(Integer, nullable=True)
    click_rate: Mapped[float | None] = mapped_column(Integer, nullable=True)

    period_start: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    period_end: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    __table_args__ = (
        Index("ix_ecommerce_metrics_period", "workspace_id", "automation_id", "period_start"),
    )