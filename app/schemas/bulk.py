from pydantic import BaseModel, Field, model_validator


class BulkSendRequest(BaseModel):
    """For WhatsApp Cloud, use template_id with an approved Meta template (required in API route)."""

    message_template: str = Field(default="", max_length=4096)
    contact_ids: list[int] = Field(min_length=1)
    template_id: int | None = None

    @model_validator(mode="after")
    def require_message_or_template_placeholder(self):
        if self.template_id is None and not self.message_template.strip():
            raise ValueError(
                "message_template cannot be empty when template_id is not provided",
            )
        return self


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
