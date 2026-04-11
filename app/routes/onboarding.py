from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.onboarding import OnboardingStatusResponse
from app.services.billing_service import get_workspace_billing_snapshot
from app.services.meta_credential_service import get_workspace_meta_credential_summary

router = APIRouter(prefix="/onboarding", tags=["Onboarding"])


@router.get("/status", response_model=OnboardingStatusResponse)
async def get_onboarding_status(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    workspace: Workspace = Depends(get_current_workspace),
) -> OnboardingStatusResponse:
    meta = await get_workspace_meta_credential_summary(
        session=session,
        workspace_id=workspace.id,
    )
    billing = await get_workspace_billing_snapshot(
        session=session,
        workspace_id=workspace.id,
    )

    subscription_active = billing.subscription_status.value == "active"
    meta_connected = meta is not None

    return OnboardingStatusResponse(
        user_id=current_user.id,
        workspace_id=workspace.id,
        workspace_name=workspace.name,
        workspace_created=True,
        meta_connected=meta_connected,
        subscription_active=subscription_active,
        ready=meta_connected and subscription_active,
    )
