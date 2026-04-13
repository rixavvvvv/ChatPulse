from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.meta_credential import MetaConnectRequest, MetaStatusResponse
from app.services.meta_credential_service import (
    ensure_waba_app_subscription,
    get_subscribed_app_links,
    get_waba_subscribed_apps,
    get_workspace_meta_credential_summary,
    get_workspace_meta_credentials,
    upsert_workspace_meta_credential,
)
from app.services.whatsapp_service import ApiError, validate_meta_cloud_credentials

router = APIRouter(prefix="/meta", tags=["Meta"])
settings = get_settings()


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

        subscribed_apps = await ensure_waba_app_subscription(
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


@router.get("/subscribed-apps")
async def get_meta_subscribed_apps(
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    credentials = await get_workspace_meta_credentials(workspace.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta credentials are not configured for this workspace",
        )

    try:
        data = await get_waba_subscribed_apps(
            access_token=credentials.access_token,
            business_account_id=credentials.business_account_id,
        )
        return {
            "data": data,
            "links": get_subscribed_app_links(data),
            # Meta subscribed_apps response does not expose webhook callback URL,
            # so callback host matching cannot be reliably inferred here.
            "callback_host_matches_public_base_url": None,
            "public_base_url": settings.public_base_url,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )


@router.post("/subscribe-webhook")
async def subscribe_meta_webhook(
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    credentials = await get_workspace_meta_credentials(workspace.id)
    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta credentials are not configured for this workspace",
        )

    try:
        data = await ensure_waba_app_subscription(
            access_token=credentials.access_token,
            business_account_id=credentials.business_account_id,
        )
        return {
            "data": data,
            "links": get_subscribed_app_links(data),
            # Meta subscribed_apps response does not expose webhook callback URL,
            # so callback host matching cannot be reliably inferred here.
            "callback_host_matches_public_base_url": None,
            "public_base_url": settings.public_base_url,
        }
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
