from datetime import datetime

from pydantic import BaseModel, Field


class ContactImportCreateResponse(BaseModel):
    job_id: int
    celery_task_id: str | None


class ContactImportJobResponse(BaseModel):
    id: int
    status: str
    total_rows: int
    processed_rows: int
    inserted_rows: int
    skipped_rows: int
    failed_rows: int
    error_message: str | None
    created_at: datetime
    completed_at: datetime | None


class ContactImportRowErrorResponse(BaseModel):
    row_number: int
    error: str
    raw: dict = Field(default_factory=dict)


class ContactImportJobErrorsResponse(BaseModel):
    job_id: int
    errors: list[ContactImportRowErrorResponse]

