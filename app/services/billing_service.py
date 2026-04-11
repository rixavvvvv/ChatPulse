from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.plan import Plan
from app.models.usage_tracking import UsageTracking
from app.models.user_subscription import UserSubscription, UserSubscriptionStatus
from app.models.workspace import Workspace
from app.services.usage_tracking_service import get_current_billing_cycle


class BillingLimitExceeded(Exception):
    def __init__(
        self,
        *,
        plan_name: str,
        message_limit: int,
        messages_sent: int,
        requested_count: int,
        reason: str | None = None,
    ):
        self.plan_name = plan_name
        self.message_limit = message_limit
        self.messages_sent = messages_sent
        self.requested_count = requested_count
        self.reason = reason

        if reason:
            detail = reason
        else:
            remaining = max(0, message_limit - messages_sent)
            detail = (
                f"Billing limit exceeded for plan '{plan_name}'. "
                f"Remaining messages in cycle: {remaining}. Requested: {requested_count}."
            )

        super().__init__(detail)


@dataclass(frozen=True)
class WorkspaceBillingSnapshot:
    workspace_id: int
    user_id: int
    billing_cycle: str
    plan_name: str
    subscription_status: UserSubscriptionStatus
    message_limit: int
    messages_sent: int

    @property
    def remaining_messages(self) -> int:
        return max(0, self.message_limit - self.messages_sent)


async def get_workspace_billing_snapshot(
    session: AsyncSession,
    *,
    workspace_id: int,
    billing_cycle: str | None = None,
) -> WorkspaceBillingSnapshot:
    cycle = billing_cycle or get_current_billing_cycle()

    workspace = await session.get(Workspace, workspace_id)
    if workspace is None:
        raise ValueError("Workspace not found")

    subscription_stmt = select(UserSubscription).where(
        UserSubscription.user_id == workspace.owner_id,
    )
    subscription = (await session.execute(subscription_stmt)).scalar_one_or_none()

    plan: Plan | None = None
    subscription_status = UserSubscriptionStatus.active

    if subscription is not None:
        plan = await session.get(Plan, subscription.plan_id)
        subscription_status = subscription.status

    if plan is None:
        free_plan_stmt = select(Plan).where(Plan.name == "free")
        plan = (await session.execute(free_plan_stmt)).scalar_one_or_none()

    if plan is None:
        raise ValueError("No plan configured for billing")

    usage_stmt = select(UsageTracking).where(
        UsageTracking.workspace_id == workspace_id,
        UsageTracking.billing_cycle == cycle,
    )
    usage = (await session.execute(usage_stmt)).scalar_one_or_none()

    return WorkspaceBillingSnapshot(
        workspace_id=workspace_id,
        user_id=workspace.owner_id,
        billing_cycle=cycle,
        plan_name=plan.name,
        subscription_status=subscription_status,
        message_limit=plan.message_limit,
        messages_sent=(usage.messages_sent if usage else 0),
    )


async def ensure_workspace_can_send(
    session: AsyncSession,
    *,
    workspace_id: int,
    requested_count: int = 1,
) -> WorkspaceBillingSnapshot:
    snapshot = await get_workspace_billing_snapshot(
        session=session,
        workspace_id=workspace_id,
    )

    if snapshot.subscription_status != UserSubscriptionStatus.active:
        raise BillingLimitExceeded(
            plan_name=snapshot.plan_name,
            message_limit=snapshot.message_limit,
            messages_sent=snapshot.messages_sent,
            requested_count=requested_count,
            reason=(
                "Subscription is not active. "
                f"Current status: {snapshot.subscription_status.value}."
            ),
        )

    if snapshot.messages_sent + requested_count > snapshot.message_limit:
        raise BillingLimitExceeded(
            plan_name=snapshot.plan_name,
            message_limit=snapshot.message_limit,
            messages_sent=snapshot.messages_sent,
            requested_count=requested_count,
        )

    return snapshot
