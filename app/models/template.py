from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class TemplateStatus(str, Enum):
    draft = "draft"
    approved = "approved"
    pending = "pending"
    rejected = "rejected"


class TemplateCategory(str, Enum):
    MARKETING = "MARKETING"
    UTILITY = "UTILITY"
    AUTHENTICATION = "AUTHENTICATION"


class TemplateHeaderType(str, Enum):
    none = "none"
    text = "text"
    image = "image"
    video = "video"
    document = "document"


class Template(Base):
    __tablename__ = "templates"
    __table_args__ = (
        UniqueConstraint("workspace_id", "name",
                         name="uq_templates_workspace_name"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(
        String(32), nullable=False, default="en_US")
    category: Mapped[str] = mapped_column(
        String(32), nullable=False, default=TemplateCategory.MARKETING.value)
    variables: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list)
    header_type: Mapped[str] = mapped_column(
        String(16), nullable=False, default=TemplateHeaderType.none.value)
    header_content: Mapped[str | None] = mapped_column(Text, nullable=True)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_examples: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, default=list)
    footer_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    buttons: Mapped[list[dict[str, str]]] = mapped_column(
        JSONB, nullable=False, default=list)
    status: Mapped[TemplateStatus] = mapped_column(
        SqlEnum(TemplateStatus, name="template_status"),
        nullable=False,
        default=TemplateStatus.draft,
    )
    meta_template_id: Mapped[str | None] = mapped_column(
        String(128), nullable=True)
    rejection_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
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
