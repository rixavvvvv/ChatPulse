from datetime import datetime
from enum import Enum

from sqlalchemy import DateTime, Enum as SqlEnum, ForeignKey, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class MembershipRole(str, Enum):
    admin = "admin"
    member = "member"


class Membership(Base):
    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint("user_id", "workspace_id",
                         name="uq_memberships_user_workspace"),
    )

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id"), nullable=False, index=True)
    workspace_id: Mapped[int] = mapped_column(
        ForeignKey("workspaces.id"), nullable=False, index=True)
    role: Mapped[MembershipRole] = mapped_column(
        SqlEnum(MembershipRole, name="membership_role"),
        nullable=False,
        default=MembershipRole.member,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
