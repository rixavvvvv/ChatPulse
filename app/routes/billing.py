from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.billing import BillingUsageResponse
from app.services.billing_service import get_workspace_billing_snapshot

router = APIRouter(prefix="/billing", tags=["Billing"])


@router.get("/usage", response_model=BillingUsageResponse)
async def get_billing_usage(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> BillingUsageResponse:
    snapshot = await get_workspace_billing_snapshot(
        session=session,
        workspace_id=workspace.id,
    )
    return BillingUsageResponse(
        workspace_id=workspace.id,
        billing_cycle=snapshot.billing_cycle,
        plan_name=snapshot.plan_name,
        subscription_status=snapshot.subscription_status,
        message_limit=snapshot.message_limit,
        messages_sent=snapshot.messages_sent,
        remaining_messages=snapshot.remaining_messages,
    )
