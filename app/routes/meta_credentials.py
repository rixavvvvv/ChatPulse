from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.meta_credential import MetaConnectRequest, MetaStatusResponse
from app.services.meta_credential_service import (
    get_workspace_meta_credential_summary,
    upsert_workspace_meta_credential,
)
from app.services.whatsapp_service import ApiError, validate_meta_cloud_credentials

router = APIRouter(prefix="/meta", tags=["Meta"])


@router.post("/connect", response_model=MetaStatusResponse)
async def connect_meta_credentials(
    payload: MetaConnectRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> MetaStatusResponse:
    try:
        await validate_meta_cloud_credentials(
            phone_number_id=payload.phone_number_id,
            business_account_id=payload.business_account_id,
            access_token=payload.access_token,
        )

        record = await upsert_workspace_meta_credential(
            session=session,
            workspace_id=workspace.id,
            phone_number_id=payload.phone_number_id,
            access_token=payload.access_token,
            business_account_id=payload.business_account_id,
        )
        return MetaStatusResponse(
            phone_number_id=record.phone_number_id,
            business_account_id=record.business_account_id,
            is_connected=True,
        )
    except ApiError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY if exc.retryable else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        )


@router.get("/status", response_model=MetaStatusResponse)
async def get_meta_status(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> MetaStatusResponse:
    record = await get_workspace_meta_credential_summary(
        session=session,
        workspace_id=workspace.id,
    )
    if not record:
        return MetaStatusResponse(
            is_connected=False,
        )

    return MetaStatusResponse(
        phone_number_id=record.phone_number_id,
        business_account_id=record.business_account_id,
        is_connected=True,
    )
