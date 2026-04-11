from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CampaignContactDeliveryStatus(str, Enum):
    pending = "pending"
    sent = "sent"
    failed = "failed"
    skipped = "skipped"


class CampaignFailureClassification(str, Enum):
    invalid_number = "invalid_number"
    api_error = "api_error"
    rate_limit = "rate_limit"


class CampaignContact(Base):
    __tablename__ = "campaign_contacts"
    __table_args__ = (
        UniqueConstraint("campaign_id", "phone",
                         name="uq_campaign_contacts_campaign_phone"),
        UniqueConstraint("campaign_id", "idempotency_key",
                         name="uq_campaign_contacts_campaign_idempotency"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    campaign_id: Mapped[int] = mapped_column(
        ForeignKey("campaigns.id"),
        nullable=False,
        index=True,
    )
    source_contact_id: Mapped[int | None] = mapped_column(
        ForeignKey("contacts.id"),
        nullable=True,
        index=True,
    )
    idempotency_key: Mapped[str] = mapped_column(
        String(96), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    delivery_status: Mapped[CampaignContactDeliveryStatus] = mapped_column(
        SqlEnum(CampaignContactDeliveryStatus,
                name="campaign_contact_delivery_status"),
        nullable=False,
        default=CampaignContactDeliveryStatus.pending,
    )
    failure_classification: Mapped[CampaignFailureClassification | None] = mapped_column(
        SqlEnum(CampaignFailureClassification,
                name="campaign_failure_classification"),
        nullable=True,
    )
    attempt_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
