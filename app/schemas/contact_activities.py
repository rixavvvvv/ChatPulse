from datetime import datetime

from pydantic import BaseModel, ConfigDict


class ContactActivityResponse(BaseModel):
    id: int
    contact_id: int
    actor_user_id: int | None
    type: str
    payload: dict
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)

