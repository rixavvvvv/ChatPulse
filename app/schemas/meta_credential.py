from pydantic import BaseModel, Field


class MetaConnectRequest(BaseModel):
    phone_number_id: str = Field(min_length=1, max_length=64)
    access_token: str = Field(min_length=1, max_length=4096)
    business_account_id: str = Field(min_length=1, max_length=64)
    app_secret: str | None = Field(default=None, min_length=1, max_length=256)
    webhook_verify_token: str | None = Field(default=None, min_length=1, max_length=256)


class MetaStatusResponse(BaseModel):
    phone_number_id: str | None = None
    business_account_id: str | None = None
    is_connected: bool


class MetaCredentialSummary(BaseModel):
    is_connected: bool
    phone_number_id: str | None = None
    business_account_id: str | None = None
    access_token_last4: str | None = None
    app_secret_configured: bool = False
    webhook_verify_token_configured: bool = False


class MetaTokenStatusResponse(BaseModel):
    is_valid: bool
    subject_id: str | None = None
    subject_name: str | None = None
    error: str | None = None


class MetaPhoneNumberInfo(BaseModel):
    id: str
    display_phone_number: str | None = None
    verified_name: str | None = None
    quality_rating: str | None = None
    status: str | None = None
    code_verification_status: str | None = None
    platform_type: str | None = None
    throughput: str | None = None


class MetaWabaInfo(BaseModel):
    id: str | None = None
    name: str | None = None
    account_review_status: str | None = None
    health_status: str | None = None
    ownership_type: str | None = None
    message_template_namespace: str | None = None


class MetaWebhookStatusResponse(BaseModel):
    callback_url: str | None = None
    verify_token_configured: bool
    signature_validation_enabled: bool
    links: list[str] = []
    callback_host_matches_public_base_url: bool | None = None
    public_base_url: str | None = None


class MetaHealthSummary(BaseModel):
    status: str
    reasons: list[str] = []


class MetaConnectionResponse(BaseModel):
    credentials: MetaCredentialSummary
    waba: MetaWabaInfo | None = None
    phone_numbers: list[MetaPhoneNumberInfo] = []
    token_status: MetaTokenStatusResponse | None = None
    webhook: MetaWebhookStatusResponse | None = None
    health: MetaHealthSummary | None = None


class MetaWebhookTestRequest(BaseModel):
    verify_token: str = Field(min_length=1, max_length=256)


class MetaRotateTokenRequest(BaseModel):
    access_token: str = Field(min_length=1, max_length=4096)
