from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.meta_credential import (
    MetaConnectRequest,
    MetaConnectionResponse,
    MetaCredentialSummary,
    MetaHealthSummary,
    MetaPhoneNumberInfo,
    MetaRotateTokenRequest,
    MetaStatusResponse,
    MetaTokenStatusResponse,
    MetaWabaInfo,
    MetaWebhookStatusResponse,
    MetaWebhookTestRequest,
)
from app.services.meta_credential_service import (
    clear_workspace_meta_credentials,
    ensure_waba_app_subscription,
    fetch_phone_numbers,
    fetch_token_status,
    fetch_waba_info,
    get_subscribed_app_links,
    get_workspace_meta_credential_flags,
    get_waba_subscribed_apps,
    get_workspace_meta_credential_summary,
    get_workspace_meta_credentials,
    has_matching_callback_host,
    upsert_workspace_meta_credential,
)
from app.services.whatsapp_service import ApiError, validate_meta_cloud_credentials
from app.services.template_service import sync_all_templates_from_meta

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
            app_secret=payload.app_secret,
            webhook_verify_token=payload.webhook_verify_token,
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


@router.get("/connection", response_model=MetaConnectionResponse)
async def get_meta_connection(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> MetaConnectionResponse:
    record = await get_workspace_meta_credential_summary(
        session=session,
        workspace_id=workspace.id,
    )
    flags = await get_workspace_meta_credential_flags(
        session=session,
        workspace_id=workspace.id,
    )

    if not record:
        return MetaConnectionResponse(
            credentials=MetaCredentialSummary(
                is_connected=False,
                access_token_last4=flags.get("access_token_last4"),
                app_secret_configured=bool(flags.get("app_secret_configured")),
                webhook_verify_token_configured=bool(
                    flags.get("webhook_verify_token_configured")
                ),
            ),
            phone_numbers=[],
        )

    creds = await get_workspace_meta_credentials(workspace.id)
    phone_numbers: list[MetaPhoneNumberInfo] = []
    waba_info: MetaWabaInfo | None = None
    token_status: MetaTokenStatusResponse | None = None
    webhook_status: MetaWebhookStatusResponse | None = None
    reasons: list[str] = []

    if creds:
        try:
            waba_payload = await fetch_waba_info(
                access_token=creds.access_token,
                business_account_id=creds.business_account_id,
            )
            waba_info = MetaWabaInfo(
                id=str(waba_payload.get("id") or ""),
                name=waba_payload.get("name"),
                account_review_status=waba_payload.get("account_review_status"),
                health_status=waba_payload.get("health_status"),
                ownership_type=waba_payload.get("ownership_type"),
                message_template_namespace=waba_payload.get("message_template_namespace"),
            )
        except Exception as exc:
            reasons.append(str(exc))

        try:
            phone_payload = await fetch_phone_numbers(
                access_token=creds.access_token,
                business_account_id=creds.business_account_id,
            )
            for item in phone_payload:
                if not isinstance(item, dict):
                    continue
                if not item.get("id"):
                    continue
                phone_numbers.append(
                    MetaPhoneNumberInfo(
                        id=str(item.get("id")),
                        display_phone_number=item.get("display_phone_number"),
                        verified_name=item.get("verified_name"),
                        quality_rating=item.get("quality_rating"),
                        status=item.get("status"),
                        code_verification_status=item.get("code_verification_status"),
                        platform_type=item.get("platform_type"),
                        throughput=item.get("throughput"),
                    )
                )
        except Exception as exc:
            reasons.append(str(exc))

        try:
            token_payload = await fetch_token_status(access_token=creds.access_token)
            token_status = MetaTokenStatusResponse(
                is_valid=True,
                subject_id=str(token_payload.get("id") or ""),
                subject_name=token_payload.get("name"),
            )
        except Exception as exc:
            token_status = MetaTokenStatusResponse(
                is_valid=False,
                error=str(exc),
            )
            reasons.append(str(exc))

        try:
            subscribed_apps = await get_waba_subscribed_apps(
                access_token=creds.access_token,
                business_account_id=creds.business_account_id,
            )
            links = get_subscribed_app_links(subscribed_apps)
            callback_url = (
                f"{settings.public_base_url}/webhook/meta"
                if settings.public_base_url
                else None
            )
            webhook_status = MetaWebhookStatusResponse(
                callback_url=callback_url,
                verify_token_configured=bool(
                    settings.meta_webhook_verify_token or record.webhook_verify_token
                ),
                signature_validation_enabled=bool(
                    settings.meta_app_secret or record.app_secret
                ),
                links=links,
                callback_host_matches_public_base_url=has_matching_callback_host(
                    subscribed_apps=subscribed_apps,
                    public_base_url=settings.public_base_url,
                ),
                public_base_url=settings.public_base_url,
            )
        except Exception as exc:
            webhook_status = MetaWebhookStatusResponse(
                callback_url=(
                    f"{settings.public_base_url}/webhook/meta"
                    if settings.public_base_url
                    else None
                ),
                verify_token_configured=bool(
                    settings.meta_webhook_verify_token or record.webhook_verify_token
                ),
                signature_validation_enabled=bool(
                    settings.meta_app_secret or record.app_secret
                ),
                links=[],
                callback_host_matches_public_base_url=None,
                public_base_url=settings.public_base_url,
            )
            reasons.append(str(exc))

    status = "healthy"
    if reasons:
        status = "degraded"

    return MetaConnectionResponse(
        credentials=MetaCredentialSummary(
            is_connected=True,
            phone_number_id=record.phone_number_id,
            business_account_id=record.business_account_id,
            access_token_last4=flags.get("access_token_last4"),
            app_secret_configured=bool(flags.get("app_secret_configured")),
            webhook_verify_token_configured=bool(
                flags.get("webhook_verify_token_configured")
            ),
        ),
        waba=waba_info,
        phone_numbers=phone_numbers,
        token_status=token_status,
        webhook=webhook_status,
        health=MetaHealthSummary(status=status, reasons=reasons),
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


@router.post("/validate")
async def validate_meta_credentials(
    payload: MetaConnectRequest,
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    _ = workspace
    try:
        await validate_meta_cloud_credentials(
            phone_number_id=payload.phone_number_id,
            business_account_id=payload.business_account_id,
            access_token=payload.access_token,
        )
        return {"ok": True}
    except ApiError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY if exc.retryable else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        )


@router.post("/webhook-test")
async def test_webhook_verify_token(
    payload: MetaWebhookTestRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    record = await get_workspace_meta_credential_summary(
        session=session,
        workspace_id=workspace.id,
    )
    expected = settings.meta_webhook_verify_token
    if not expected and record:
        creds = await get_workspace_meta_credentials(workspace.id)
        if creds and creds.webhook_verify_token:
            expected = creds.webhook_verify_token

    if not expected:
        return {"ok": False, "reason": "No verify token configured"}

    return {"ok": payload.verify_token.strip() == expected.strip()}


@router.post("/rotate-token")
async def rotate_meta_access_token(
    payload: MetaRotateTokenRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    record = await get_workspace_meta_credential_summary(
        session=session,
        workspace_id=workspace.id,
    )
    if not record:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Meta credentials are not configured for this workspace",
        )

    try:
        await validate_meta_cloud_credentials(
            phone_number_id=record.phone_number_id,
            business_account_id=record.business_account_id,
            access_token=payload.access_token,
        )
        await upsert_workspace_meta_credential(
            session=session,
            workspace_id=workspace.id,
            phone_number_id=record.phone_number_id,
            access_token=payload.access_token,
            business_account_id=record.business_account_id,
        )
        return {"ok": True}
    except ApiError as exc:
        raise HTTPException(
            status_code=(
                status.HTTP_502_BAD_GATEWAY if exc.retryable else status.HTTP_400_BAD_REQUEST
            ),
            detail=str(exc),
        )


@router.post("/disconnect")
async def disconnect_meta_credentials(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict:
    await clear_workspace_meta_credentials(session=session, workspace_id=workspace.id)
    return {"ok": True}


@router.post("/sync-templates")
async def sync_meta_templates(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> dict[str, int]:
    try:
        result = await sync_all_templates_from_meta(
            session=session,
            workspace_id=workspace.id,
        )
        return {
            "created": int(result.get("created", 0)),
            "updated": int(result.get("updated", 0)),
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
