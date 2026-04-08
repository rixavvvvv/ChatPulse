from pydantic import BaseModel, Field


class MetaConnectRequest(BaseModel):
    phone_number_id: str = Field(min_length=1, max_length=64)
    access_token: str = Field(min_length=1, max_length=4096)
    business_account_id: str = Field(min_length=1, max_length=64)


class MetaStatusResponse(BaseModel):
    phone_number_id: str | None = None
    business_account_id: str | None = None
    is_connected: bool
