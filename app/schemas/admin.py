from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole
from app.models.user_subscription import UserSubscriptionStatus


class AdminCreateUserRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    role: UserRole = UserRole.user
    subscription_plan: str = Field(default="free", min_length=1, max_length=64)
    is_active: bool = True


class AdminUserRoleUpdateRequest(BaseModel):
    role: UserRole


class AdminUserSubscriptionUpdateRequest(BaseModel):
    plan_id: int = Field(gt=0)
    status: UserSubscriptionStatus = UserSubscriptionStatus.active


class AdminUserActivationUpdateRequest(BaseModel):
    is_active: bool


class AdminUserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    subscription_plan: str
    is_active: bool
    plan_id: int | None = None
    subscription_status: UserSubscriptionStatus | None = None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminPlanCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=64)
    message_limit: int = Field(ge=0)
    price: Decimal = Field(ge=0)


class AdminPlanResponse(BaseModel):
    id: int
    name: str
    message_limit: int
    price: Decimal
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AdminWorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    created_at: datetime


class AdminWorkspaceUsageResponse(BaseModel):
    workspace_id: int
    workspace_name: str
    owner_id: int
    messages_sent: int
    billing_cycle: str
