from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db_session
from app.services.webhook_accept_service import accept_meta_whatsapp_webhook
from app.services.webhook_verification import (
    meta_challenge_response,
    meta_signature_valid,
    parse_json_object,
)
from app.queue.rate_limit import (
    WebhookIngestRateLimitExceeded,
    enforce_webhook_ingest_ip_limit,
)

router = APIRouter(tags=["Webhooks"])
settings = get_settings()


@router.get("/webhook/meta", response_class=PlainTextResponse)
async def verify_meta_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(
        default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
) -> PlainTextResponse:
    challenge = meta_challenge_response(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Meta webhook verification failed",
        )
    return PlainTextResponse(content=challenge, status_code=status.HTTP_200_OK)


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


async def _handle_meta_webhook_post(
    request: Request,
    session: AsyncSession,
) -> dict[str, str | int | bool | None]:
    raw_body = await request.body()

    if settings.webhook_ingest_rate_limit_per_ip_per_minute > 0:
        redis = Redis.from_url(settings.redis_url, decode_responses=True)
        try:
            client_ip = request.client.host if request.client else "unknown"
            await enforce_webhook_ingest_ip_limit(redis, client_ip)
        except WebhookIngestRateLimitExceeded as exc:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Webhook ingest rate limit exceeded",
                headers={"Retry-After": str(exc.retry_after_seconds)},
            ) from exc
        finally:
            await redis.aclose()

    if settings.meta_app_secret:
        signature = request.headers.get(
            "X-Hub-Signature-256") or request.headers.get("x-hub-signature-256")
        if not signature:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header",
            )
        if not meta_signature_valid(raw_body=raw_body, signature_header=signature):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )

    try:
        payload = parse_json_object(raw_body)
    except (UnicodeDecodeError, ValueError) as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid webhook payload",
        ) from exc

    accepted = await accept_meta_whatsapp_webhook(
        session=session,
        raw_body=raw_body,
        payload=payload,
        request_headers=request.headers,
    )
    return accepted


@router.post("/webhook/meta")
async def receive_meta_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | int | bool | None]:
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
    challenge = meta_challenge_response(
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )
    if challenge is None:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Meta webhook verification failed",
        )
    return PlainTextResponse(content=challenge, status_code=status.HTTP_200_OK)


@router.post("/whatsapp-webhook/{webhook_id}")
async def receive_meta_webhook_alias(
    webhook_id: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | int | bool | None]:
    _ = webhook_id
    return await _handle_meta_webhook_post(request=request, session=session)
