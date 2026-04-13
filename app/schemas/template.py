from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from app.models.template import TemplateCategory, TemplateHeaderType, TemplateStatus


class TemplateButtonInput(BaseModel):
    type: Literal["quick_reply", "url", "phone_number", "copy_code"]
    text: str = Field(min_length=1, max_length=25)
    value: str = Field(default="", max_length=256)


class TemplateCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    language: str = Field(default="en_US", min_length=2, max_length=32)
    category: TemplateCategory = TemplateCategory.MARKETING
    header_type: TemplateHeaderType = TemplateHeaderType.none
    header_content: str | None = Field(default=None, max_length=1024)
    body_text: str = Field(min_length=1, max_length=4096)
    variables: list[str] = Field(default_factory=list)
    sample_values: list[str] = Field(default_factory=list)
    footer_text: str | None = Field(default=None, max_length=512)
    buttons: list[TemplateButtonInput] = Field(default_factory=list)


class TemplateSubmitResponse(BaseModel):
    id: int
    status: TemplateStatus
    meta_template_id: str | None


class TemplateStatusUpdateRequest(BaseModel):
    status: TemplateStatus


class TemplateResponse(BaseModel):
    id: int
    name: str
    language: str
    category: TemplateCategory
    header_type: TemplateHeaderType
    header_content: str | None
    body_text: str
    variables: list[str]
    sample_values: list[str]
    footer_text: str | None
    buttons: list[TemplateButtonInput]
    status: TemplateStatus
    meta_template_id: str | None
    rejection_reason: str | None
    created_at: datetime
    updated_at: datetime
