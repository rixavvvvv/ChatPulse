from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, String, func, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserRole(str, Enum):
    super_admin = "super_admin"
    user = "user"


class SubscriptionPlan(str, Enum):
    free = "free"
    pro = "pro"
    business = "business"
    enterprise = "enterprise"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    email: Mapped[str] = mapped_column(
        String(320), unique=True, index=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=UserRole.user.value,
        server_default=UserRole.user.value,
        index=True,
    )
    subscription_plan: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
        default=SubscriptionPlan.free.value,
        server_default=SubscriptionPlan.free.value,
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=True,
        server_default=text("true"),
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
