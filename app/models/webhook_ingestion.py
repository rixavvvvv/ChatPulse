from datetime import datetime
from enum import Enum

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class WebhookSource(str, Enum):
    meta_whatsapp = "meta_whatsapp"
    shopify_orders = "shopify_orders"


class WebhookIngestionStatus(str, Enum):
    received = "received"
    verified = "verified"
    queued = "queued"
    processing = "processing"
    completed = "completed"
    failed = "failed"
    dead = "dead"


class WebhookIngestion(Base):
    """
    Raw webhook receipt + pipeline state (ingestion → queue → dispatch).

    Idempotency is enforced at two levels:
    1. Redis (fast path): SETNX on provider_event_id for in-flight dedupe
    2. PostgreSQL (authoritative): UNIQUE constraint on (source, provider_event_id)

    This dual-layer approach ensures:
    - No duplicate processing even with concurrent workers
    - No duplicate processing after worker crashes
    - Replay-safe handling of failed ingestions
    """

    __tablename__ = "webhook_ingestions"
    __table_args__ = (
        # PRIMARY IDEMPOTENCY: unique per provider event
        # This prevents duplicate webhooks from the same source
        UniqueConstraint(
            "source",
            "provider_event_id",
            name="uq_webhook_source_provider_event_id",
        ),
        # Index for fast dedupe lookups
        Index("ix_webhook_ingestions_source_status", "source", "processing_status"),
        # Index for replay queries
        Index("ix_webhook_ingestions_status_replay", "processing_status", "replay_count"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    source: Mapped[str] = mapped_column(String(32), nullable=False, index=True)

    # Provider-level idempotency key
    # For Meta: the wamid/message ID from the webhook
    # For Shopify: the order ID or checkout ID
    # Set to dedupe_key hash if provider doesn't provide stable ID
    provider_event_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
        index=True,
    )

    # Deduplication key (SHA256 of payload + context)
    # Used for short-window dedupe and replay tracking
    dedupe_key: Mapped[str] = mapped_column(String(128), nullable=False, index=True)

    store_identifier: Mapped[str | None] = mapped_column(
        String(255), nullable=True, index=True
    )
    payload_sha256: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    payload_json: Mapped[dict | list] = mapped_column(JSONB, nullable=False)
    raw_body: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    provider_signature: Mapped[str | None] = mapped_column(Text, nullable=True)
    headers_meta: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    verification_passed: Mapped[bool] = mapped_column(nullable=False, default=False)
    verification_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    processing_status: Mapped[str] = mapped_column(
        String(32), nullable=False, index=True, default=WebhookIngestionStatus.received.value
    )
    dispatch_result: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    workspace_id: Mapped[int | None] = mapped_column(
        ForeignKey("workspaces.id"), nullable=True, index=True
    )
    replay_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_replay_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    received_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    processing_started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
