from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


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


class AbandonedCartConfig(BaseModel):
    cart_idle_minutes: int = Field(60, description="Minutes after cart abandonment to trigger")
    recovery_window_hours: int = Field(72, description="Hours to attempt recovery")
    include_abandoned_items: bool = True


class OrderConfirmationConfig(BaseModel):
    send_immediately: bool = True
    include_order_details: bool = True
    include_estimated_delivery: bool = True
    attach_invoice: bool = False


class ShipmentConfig(BaseModel):
    notify_on: list[str] = Field(
        default_factory=lambda: ["created", "in_transit", "delivered"],
        description="Events to notify about"
    )
    include_tracking_link: bool = True
    carrier_name_field: str = "carrier"


class CodVerificationConfig(BaseModel):
    verification_window_hours: int = Field(24, description="Hours to complete COD verification")
    reminder_after_hours: int = Field(12, description="Send reminder after X hours")
    max_reminders: int = Field(2, description="Maximum reminder attempts")


class AutomationTriggerConfig(BaseModel):
    trigger_type: AutomationTriggerType
    config: dict[str, Any] = Field(default_factory=dict)


class AutomationActionConfig(BaseModel):
    action_type: str = Field("send_template_message")
    template_id: int | None = None
    fallback_message: str | None = None


class EcommerceAutomationCreate(BaseModel):
    name: str = Field(..., max_length=255)
    description: str | None = None
    automation_type: EcommerceAutomationType
    trigger_config: AutomationTriggerConfig
    action_config: AutomationActionConfig
    delay_seconds: int = 0
    delay_type: str | None = None
    segment_id: int | None = None
    template_id: int | None = None
    priority: int = 0
    max_retries: int = 3


class EcommerceAutomationUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    status: EcommerceAutomationStatus | None = None
    trigger_config: AutomationTriggerConfig | None = None
    action_config: AutomationActionConfig | None = None
    delay_seconds: int | None = None
    delay_type: str | None = None
    segment_id: int | None = None
    template_id: int | None = None
    priority: int | None = None
    max_retries: int | None = None


class EcommerceAutomationResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    description: str | None
    automation_type: EcommerceAutomationType
    trigger_type: AutomationTriggerType
    status: EcommerceAutomationStatus
    trigger_config: dict[str, Any]
    action_config: dict[str, Any]
    delay_seconds: int
    delay_type: str | None
    segment_id: int | None
    template_id: int | None
    priority: int
    max_retries: int
    created_by: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EcommerceAutomationListResponse(BaseModel):
    id: int
    workspace_id: int
    name: str
    automation_type: EcommerceAutomationType
    trigger_type: AutomationTriggerType
    status: EcommerceAutomationStatus
    priority: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EcommerceAutomationExecutionCreate(BaseModel):
    automation_id: int
    order_id: str | None = None
    cart_id: str | None = None
    contact_id: int | None = None
    trigger_data: dict[str, Any] = Field(default_factory=dict)


class EcommerceAutomationExecutionResponse(BaseModel):
    id: int
    workspace_id: int
    automation_id: int
    order_id: str | None
    cart_id: str | None
    contact_id: int | None
    execution_id: str
    status: ExecutionStatus
    trigger_data: dict[str, Any]
    message_payload: dict[str, Any]
    delayed_execution_id: int | None
    message_id: str | None
    error: str | None
    retry_count: int
    sent_at: datetime | None
    delivered_at: datetime | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EcommerceAttributionCreate(BaseModel):
    contact_id: int
    order_id: str
    cart_id: str | None = None
    attribution_model: AttributionModel
    touchpoints: list[dict[str, Any]] = Field(default_factory=list)
    revenue: float = 0
    currency: str = "USD"
    converted: bool = False


class EcommerceAttributionResponse(BaseModel):
    id: int
    workspace_id: int
    contact_id: int
    order_id: str
    cart_id: str | None
    attribution_model: AttributionModel
    touchpoints: list[dict[str, Any]]
    revenue: float
    currency: str
    converted: bool
    conversion_timestamp: datetime | None
    first_touch_id: str | None
    last_touch_id: str | None
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class EcommerceAutomationStats(BaseModel):
    total_automations: int
    active_automations: int
    paused_automations: int
    total_executions: int
    sent_count: int
    delivered_count: int
    failed_count: int
    conversion_count: int
    total_revenue: float
    avg_recovery_rate: float | None
    avg_conversion_rate: float | None


class AutomationExecutionStats(BaseModel):
    automation_id: int
    automation_name: str
    automation_type: EcommerceAutomationType
    scheduled_count: int
    sent_count: int
    delivered_count: int
    failed_count: int
    conversion_count: int
    revenue: float
    recovery_rate: float | None
    conversion_rate: float | None
    avg_time_to_send_seconds: float | None


class RecoveryMetrics(BaseModel):
    carts_abandoned: int
    recovery_attempts: int
    recovered_orders: int
    recovery_rate: float
    revenue_recovered: float
    avg_recovery_time_hours: float | None


class ConversionAttribution(BaseModel):
    contact_id: int
    order_id: str
    revenue: float
    attribution_model: AttributionModel
    converted_touchpoints: list[str] = Field(default_factory=list)
    first_touch_source: str | None = None
    last_touch_source: str | None = None