from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Contact(Base):
    __tablename__ = "contacts"
    __table_args__ = (
        UniqueConstraint("workspace_id", "phone",
                         name="uq_contacts_workspace_phone"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    phone: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    tags: Mapped[list[str]] = mapped_column(
        ARRAY(String), nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
