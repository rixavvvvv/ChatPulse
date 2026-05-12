from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ContactNoteCreateRequest(BaseModel):
    body: str = Field(min_length=1, max_length=10000)


class ContactNoteResponse(BaseModel):
    id: int
    contact_id: int
    author_user_id: int | None
    body: str
    created_at: datetime
    deleted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)

