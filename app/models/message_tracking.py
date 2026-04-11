from datetime import datetime
from enum import Enum
from typing import Any

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MessageTrackingStatus(str, Enum):
    sent = "sent"
    delivered = "delivered"
    read = "read"
    failed = "failed"


class MessageTracking(Base):
    __tablename__ = "message_tracking"
    __table_args__ = (
        UniqueConstraint("provider_message_id",
                         name="uq_message_tracking_provider_message_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=True,
        index=True,
    )
    campaign_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("campaign_contacts.id"),
        nullable=True,
        index=True,
    )
    provider_message_id: Mapped[str] = mapped_column(
        String(128), nullable=False, index=True)
    recipient_phone: Mapped[str | None] = mapped_column(
        String(32), nullable=True)
    current_status: Mapped[MessageTrackingStatus] = mapped_column(
        SqlEnum(MessageTrackingStatus, name="message_tracking_status"),
        nullable=False,
        default=MessageTrackingStatus.sent,
    )
    sent_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    delivered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    failed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    last_webhook_payload: Mapped[dict[str, Any] |
                                 None] = mapped_column(JSONB, nullable=True)
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
