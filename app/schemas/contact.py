from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContactCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    phone: str = Field(min_length=8, max_length=32)
    tags: list[str] = Field(default_factory=list)


class ContactUploadResponse(BaseModel):
    contacts_added: int
    contacts_skipped: int


class ContactResponse(BaseModel):
    id: int
    name: str
    phone: str
    tags: list[str]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)
