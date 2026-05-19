from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.services.segment_filter_dsl import normalize_definition, validate_definition


class SegmentCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    definition: dict = Field(default_factory=dict)

    @field_validator("definition")
    @classmethod
    def _validate_definition(cls, value: dict) -> dict:
        normalized = normalize_definition(value)
        validate_definition(normalized)
        return normalized


class SegmentUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    definition: dict | None = Field(default=None)

    @field_validator("definition")
    @classmethod
    def _validate_definition(cls, value: dict | None) -> dict | None:
        if value is None:
            return value
        normalized = normalize_definition(value)
        validate_definition(normalized)
        return normalized


class SegmentPreviewRequest(BaseModel):
    definition: dict = Field(default_factory=dict)

    @field_validator("definition")
    @classmethod
    def _validate_definition(cls, value: dict) -> dict:
        normalized = normalize_definition(value)
        validate_definition(normalized)
        return normalized


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

