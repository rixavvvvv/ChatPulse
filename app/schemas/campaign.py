from datetime import datetime

from pydantic import BaseModel, Field

from app.models.campaign import CampaignStatus


class CampaignCreateRequest(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    template_id: int = Field(gt=0)


class CampaignAudienceBindRequest(BaseModel):
    contact_ids: list[int] = Field(min_length=1)


class CampaignAudienceBindResponse(BaseModel):
    campaign_id: int
    audience_count: int
    skipped_count: int


class CampaignQueueResponse(BaseModel):
    campaign_id: int
    status: CampaignStatus
    job_id: str


class CampaignQueueRequest(BaseModel):
    schedule_at: datetime | None = None


class CampaignResponse(BaseModel):
    id: int
    template_id: int
    name: str
    message_template: str
    status: CampaignStatus
    audience_count: int
    success_count: int
    failed_count: int
    queued_job_id: str | None
    last_error: str | None
    created_at: datetime
    updated_at: datetime


class CampaignProgressResponse(BaseModel):
    campaign_id: int
    status: CampaignStatus
    total_count: int
    processed_count: int
    sent_count: int
    failed_count: int
    skipped_count: int
    progress_percentage: float
