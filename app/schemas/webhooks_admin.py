from pydantic import BaseModel, Field


class WebhookIngestionReplayRequest(BaseModel):
    ingestion_ids: list[int] = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Primary keys of webhook_ingestions rows to requeue.",
    )


class WebhookIngestionReplayItemResponse(BaseModel):
    ingestion_id: int
    status: str | None = None
    celery_task_id: str | None = None
    replay_count: int | None = None
    error: str | None = None


class WebhookIngestionReplayResponse(BaseModel):
    results: list[WebhookIngestionReplayItemResponse]
