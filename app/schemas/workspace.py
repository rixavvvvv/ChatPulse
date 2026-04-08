from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.membership import MembershipRole


class WorkspaceCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=120)


class WorkspaceSwitchRequest(BaseModel):
    workspace_id: int = Field(gt=0)


class WorkspaceResponse(BaseModel):
    id: int
    name: str
    owner_id: int
    role: MembershipRole
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
