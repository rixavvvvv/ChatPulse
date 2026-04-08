from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MetaCredential(Base):
    __tablename__ = "meta_credentials"
    __table_args__ = (
        UniqueConstraint("workspace_id", name="uq_meta_credentials_workspace"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"),
        nullable=False,
        index=True,
    )
    phone_number_id: Mapped[str] = mapped_column(String(64), nullable=False)
    access_token: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        info={"sensitive": True},
    )
    business_account_id: Mapped[str] = mapped_column(
        String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
