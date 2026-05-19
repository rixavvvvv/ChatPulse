import logging

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db_session
from app.services.webhook_accept_service import accept_meta_whatsapp_webhook
from app.services.meta_credential_service import (
    list_all_app_secrets,
    list_all_webhook_verify_tokens,
)
from app.services.webhook_verification import (
    meta_signature_valid_with_secret,
    parse_json_object,
)
from app.queue.rate_limit import (
    WebhookIngestRateLimitExceeded,
    enforce_webhook_ingest_ip_limit,
)

router = APIRouter(tags=["Webhooks"])
settings = get_settings()
logger = logging.getLogger(__name__)


async def _resolve_verify_tokens(session: AsyncSession) -> list[str]:
    tokens: list[str] = []
    env_token = (settings.meta_webhook_verify_token or "").strip()
    if env_token:
        tokens.append(env_token)

    try:
        workspace_tokens = await list_all_webhook_verify_tokens(session)
    except Exception:
        logger.exception("meta.webhook.verify_token_resolution_failed")
        workspace_tokens = []
    tokens.extend(token.strip() for token in workspace_tokens if token and token.strip())

    # Preserve order while deduplicating
    deduped = list(dict.fromkeys(tokens))
    return deduped


async def _resolve_signature_secrets(session: AsyncSession) -> list[str]:
    secrets: list[str] = []
    env_secret = (settings.meta_app_secret or "").strip()
    if env_secret:
        secrets.append(env_secret)

    try:
        workspace_secrets = await list_all_app_secrets(session)
    except Exception:
        logger.exception("meta.webhook.app_secret_resolution_failed")
        workspace_secrets = []
    secrets.extend(secret.strip() for secret in workspace_secrets if secret and secret.strip())

    return list(dict.fromkeys(secrets))


async def _verify_meta_challenge(
    *,
    session: AsyncSession,
    hub_mode: str | None,
    hub_verify_token: str | None,
    hub_challenge: str | None,
) -> str | None:
    mode = (hub_mode or "").strip().lower()
    candidate = (hub_verify_token or "").strip()
    challenge = (hub_challenge or "").strip()

    if mode != "subscribe" or not challenge:
        logger.warning(
            "meta.webhook.verify.invalid_request",
            extra={"mode": mode or None, "has_challenge": bool(challenge)},
        )
        return None

    tokens = await _resolve_verify_tokens(session)
    if not tokens:
        logger.warning(
            "meta.webhook.verify.no_token_configured",
            extra={"mode": mode},
        )
        return None

    matched = any(candidate == token for token in tokens)
    logger.info(
        "meta.webhook.verify.attempt",
        extra={
            "mode": mode,
            "matched": matched,
            "token_candidates": len(tokens),
        },
    )
    if not matched:
        return None
    return hub_challenge or challenge


@router.get("/webhook/meta", response_class=PlainTextResponse)
async def verify_meta_webhook(
    hub_mode: str | None = Query(default=None, alias="hub.mode"),
    hub_verify_token: str | None = Query(
        default=None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(default=None, alias="hub.challenge"),
    session: AsyncSession = Depends(get_db_session),
) -> PlainTextResponse:
    challenge = await _verify_meta_challenge(
        session=session,
        hub_mode=hub_mode,
        hub_verify_token=hub_verify_token,
        hub_challenge=hub_challenge,
    )
    if challenge is not None:
        return PlainTextResponse(content=challenge, status_code=status.HTTP_200_OK)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="Meta webhook verification failed",
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


@router.get("/webhook/meta/diagnostics")
async def get_meta_webhook_diagnostics(
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | bool | int | None]:
    tokens = await _resolve_verify_tokens(session)
    secrets = await _resolve_signature_secrets(session)
    try:
        workspace_tokens = await list_all_webhook_verify_tokens(session)
    except Exception:
        workspace_tokens = []
    try:
        workspace_secrets = await list_all_app_secrets(session)
    except Exception:
        workspace_secrets = []
    mode = "healthy" if tokens else "degraded"
    return {
        "status": mode,
        "callback_url": (
            f"{settings.public_base_url}/webhook/meta"
            if settings.public_base_url
            else None
        ),
        "public_base_url": settings.public_base_url,
        "env_verify_token_configured": bool((settings.meta_webhook_verify_token or "").strip()),
        "workspace_verify_token_configured": bool(workspace_tokens),
        "resolved_verify_token_count": len(tokens),
        "env_app_secret_configured": bool((settings.meta_app_secret or "").strip()),
        "workspace_app_secret_configured": bool(workspace_secrets),
        "resolved_app_secret_count": len(secrets),
        "signature_validation_enabled": bool(secrets),
        "verification_ready": bool(tokens),
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

    secrets = await _resolve_signature_secrets(session)
    if secrets:
        signature = request.headers.get(
            "X-Hub-Signature-256") or request.headers.get("x-hub-signature-256")
        if not signature:
            logger.warning("meta.webhook.signature.missing")
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Missing X-Hub-Signature-256 header",
            )
        if not any(
            meta_signature_valid_with_secret(
                raw_body=raw_body,
                signature_header=signature,
                secret=secret,
            )
            for secret in secrets
        ):
            logger.warning(
                "meta.webhook.signature.invalid",
                extra={"secret_candidates": len(secrets)},
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid webhook signature",
            )
    else:
        logger.info("meta.webhook.signature.skipped")

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
    session: AsyncSession = Depends(get_db_session),
) -> PlainTextResponse:
    _ = webhook_id
    challenge = await _verify_meta_challenge(
        session=session,
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
