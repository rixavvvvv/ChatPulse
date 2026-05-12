from pydantic import BaseModel, Field


class EcommerceStoreCreateRequest(BaseModel):
    store_identifier: str = Field(min_length=1, max_length=255)
    webhook_secret: str = Field(min_length=8, max_length=512)
    access_token: str | None = Field(default=None, max_length=2048)


class EcommerceStoreResponse(BaseModel):
    id: int
    workspace_id: int
    store_identifier: str
    access_token_configured: bool


class EcommerceEventTemplateMapRequest(BaseModel):
    event_type: str = Field(min_length=1, max_length=64)
    template_id: int = Field(ge=1)


class EcommerceEventTemplateMapResponse(BaseModel):
    id: int
    workspace_id: int
    event_type: str
    template_id: int
