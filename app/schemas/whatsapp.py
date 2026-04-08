from pydantic import BaseModel, Field


class SendMessageRequest(BaseModel):
    phone: str = Field(min_length=8, max_length=32)
    message: str = Field(min_length=1, max_length=4096)


class SendMessageResponse(BaseModel):
    status: str
    phone: str
    provider: str
    message_id: str | None = None
