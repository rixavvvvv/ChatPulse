from pydantic import BaseModel


class OnboardingStatusResponse(BaseModel):
    user_id: int
    workspace_id: int
    workspace_name: str
    workspace_created: bool
    meta_connected: bool
    subscription_active: bool
    ready: bool
