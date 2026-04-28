import hashlib
import hmac
import json

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db_session
from app.services.webhook_service import process_meta_webhook_payload

router = APIRouter(tags=["Webhooks"])
settings = get_settings()


def _is_valid_meta_signature(raw_body: bytes, header_value: str, app_secret: str) -> bool:
    candidate = header_value.strip()
    prefix = "sha256="
    if candidate.lower().startswith(prefix):
        candidate = candidate[len(prefix):]

    if not candidate:
        return False

    computed = hmac.new(
        key=app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, candidate)


def _verify_meta_webhook_challenge(
    hub_mode: str | None,
    hub_verify_token: str | None,
    hub_challenge: str | None,
) -> PlainTextResponse:
    mode = (hub_mode or "").strip().lower()
    verify_token = (hub_verify_token or "").strip()
    challenge = (hub_challenge or "").strip()

    if mode == "subscribe" and verify_token == settings.meta_webhook_verify_token and challenge:
        return PlainTextResponse(content=hub_challenge, status_code=status.HTTP_200_OK)

    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Meta webhook verification failed",
    )


async def _handle_meta_webhook_post(
    request: Request,
    session: AsyncSession,
) -> dict[str, int | str]:
    raw_body = await request.body()

    if settings.meta_app_secret:
        signature = request.headers.get(
            "X-Hub-Signature-256") or request.headers.get("x-hub-signature-256")
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header",
            )
        if not _is_valid_meta_signature(
            raw_body=raw_body,
            header_value=signature,
            app_secret=settings.meta_app_secret,
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON payload",
        ) from exc

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        )

    object_type = payload.get("object")
    if object_type is not None and object_type != "whatsapp_business_account":
        return {
            "status": "ignored",
            "processed": 0,
            "ignored": 0,
            "unknown_message": 0,
        }

    result = await process_meta_webhook_payload(session=session, payload=payload)
    return {
        "status": "ok",
        "processed": result.processed,
        "ignored": result.ignored,
        "unknown_message": result.unknown_message,
    }


@router.get("/webhook/meta", response_class=PlainTextResponse)
async def verify_meta_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(
        default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    return _verify_meta_webhook_challenge(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )


@router.get("/webhook/meta/config")
async def get_meta_webhook_config() -> dict[str, str | bool | None]:
    callback_url = None
    if settings.public_base_url:
        callback_url = f"{settings.public_base_url}/webhook/meta"

    return {
        "callback_url": callback_url,
        "verify_token_configured": bool(settings.meta_webhook_verify_token),
        "signature_validation_enabled": bool(settings.meta_app_secret),
        "public_base_url": settings.public_base_url,
    }


@router.post("/webhook/meta")
async def receive_meta_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int | str]:
    return await _handle_meta_webhook_post(request=request, session=session)


@router.get("/whatsapp-webhook/{webhook_id}", response_class=PlainTextResponse)
async def verify_meta_webhook_alias(
    webhook_id: str,
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(
        default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    _ = webhook_id
    return _verify_meta_webhook_challenge(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )


@router.post("/whatsapp-webhook/{webhook_id}")
async def receive_meta_webhook_alias(
    webhook_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, int | str]:
    _ = webhook_id
    return await _handle_meta_webhook_post(request=request, session=session)
