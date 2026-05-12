from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, Index, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class CampaignStatus(str, Enum):
    draft = "draft"
    queued = "queued"
    running = "running"
    recovering = "recovering"  # Recovery in progress
    completed = "completed"
    failed = "failed"


class Campaign(Base):
    __tablename__ = "campaigns"
    __table_args__ = (
        Index("ix_campaigns_status_heartbeat", "status", "last_heartbeat_at"),
        Index("ix_campaigns_workspace_status", "workspace_id", "status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    message_template: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[CampaignStatus] = mapped_column(
        SqlEnum(CampaignStatus, name="campaign_status"),
        nullable=False,
        default=CampaignStatus.draft,
    )
    queued_job_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True)
    success_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    failed_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Execution recovery fields
    celery_task_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True, index=True)
    last_heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True)
    last_checkpoint_index: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    execution_lease_expires_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)
    recovery_count: Mapped[int] = mapped_column(
        Integer, nullable=False, default=0)
    last_recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True)

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
