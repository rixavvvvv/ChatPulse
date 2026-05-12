from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OrderWebhookLogStatus(str, Enum):
    success = "success"
    failed = "failed"


class EcommerceStoreConnection(Base):
    __tablename__ = "ecommerce_store_connections"
    __table_args__ = (
        UniqueConstraint(
            "store_identifier",
            name="uq_ecommerce_store_identifier",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    store_identifier: Mapped[str] = mapped_column(
        String(255),
        nullable=False,
        index=True,
    )
    webhook_secret_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    access_token_encrypted: Mapped[str | None] = mapped_column(Text, nullable=True)
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


class EcommerceEventTemplateMap(Base):
    __tablename__ = "ecommerce_event_template_maps"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "event_type",
            name="uq_ecommerce_event_template_workspace_event",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    event_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("templates.id"),
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


class OrderWebhookDeliveryLog(Base):
    __tablename__ = "order_webhook_delivery_logs"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    store_connection_id: Mapped[int | None] = mapped_column(
        ForeignKey("ecommerce_store_connections.id"),
        nullable=True,
    )
    phone: Mapped[str] = mapped_column(String(64), nullable=False)
    message_preview: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
