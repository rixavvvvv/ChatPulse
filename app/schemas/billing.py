from pydantic import BaseModel

from app.models.user_subscription import UserSubscriptionStatus


class BillingUsageResponse(BaseModel):
    workspace_id: int
    billing_cycle: str
    plan_name: str
    subscription_status: UserSubscriptionStatus
    message_limit: int
    messages_sent: int
    remaining_messages: int
