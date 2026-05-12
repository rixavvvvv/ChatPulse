from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class SegmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: dict = Field(default_factory=dict)


class SegmentPreviewRequest(BaseModel):
    definition: dict = Field(default_factory=dict)


class SegmentResponse(BaseModel):
    id: int
    name: str
    status: str
    definition: dict
    approx_size: int
    last_materialized_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SegmentPreviewResponse(BaseModel):
    estimated_count: int


class SegmentMaterializeResponse(BaseModel):
    segment_id: int
    celery_task_id: str | None

