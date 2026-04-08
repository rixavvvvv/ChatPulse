from pydantic import BaseModel, Field


class BulkSendRequest(BaseModel):
    message_template: str = Field(min_length=1, max_length=4096)
    contact_ids: list[int] = Field(min_length=1)


class BulkSendResponse(BaseModel):
    success_count: int
    failed_count: int


class BulkQueueEnqueueResponse(BaseModel):
    job_id: str
    status: str


class BulkQueueStatusResponse(BaseModel):
    job_id: str
    status: str
    success_count: int | None = None
    failed_count: int | None = None
    error: str | None = None
