from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.user import UserRole


class SignupRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    workspace_id: int
    role: UserRole


class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole
    subscription_plan: str
    is_active: bool
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
