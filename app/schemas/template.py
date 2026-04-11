from datetime import datetime

from pydantic import BaseModel, Field

from app.models.template import TemplateStatus


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    body: str = Field(min_length=1, max_length=4096)
    variables: list[str] = Field(default_factory=list)


class TemplateStatusUpdateRequest(BaseModel):
    status: TemplateStatus


class TemplateResponse(BaseModel):
    id: int
    name: str
    body: str
    variables: list[str]
    status: TemplateStatus
    created_at: datetime
    updated_at: datetime
