from pydantic import BaseModel, Field


class BulkSendRequest(BaseModel):
    message_template: str = Field(min_length=1, max_length=4096)
    contact_ids: list[int] = Field(min_length=1)


class BulkDeliveryResult(BaseModel):
    contact_id: int
    phone: str | None = None
    status: str
    provider: str | None = None
    message_id: str | None = None
    error: str | None = None


class BulkSendResponse(BaseModel):
    success_count: int
    failed_count: int
    results: list[BulkDeliveryResult] = Field(default_factory=list)


class BulkQueueEnqueueResponse(BaseModel):
    job_id: str
    status: str


class BulkQueueStatusResponse(BaseModel):
    job_id: str
    status: str
    success_count: int | None = None
    failed_count: int | None = None
    error: str | None = None
