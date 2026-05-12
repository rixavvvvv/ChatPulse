from fastapi import APIRouter, Depends, HTTPException, Request, status
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.db import get_db_session
from app.services.webhook_accept_service import accept_shopify_order_created_webhook
from app.queue.rate_limit import (
    WebhookIngestRateLimitExceeded,
    enforce_webhook_ingest_ip_limit,
)

router = APIRouter(tags=["Order webhooks"])
settings = get_settings()


async def _handle_order_webhook(
    store_identifier: str,
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

    try:
        return await accept_shopify_order_created_webhook(
            session=session,
            store_identifier=store_identifier,
            raw_body=raw_body,
            request_headers=request.headers,
        )
    except PermissionError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid webhook signature",
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/webhook/order-created")
async def receive_order_created_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | int | bool | None]:
    store = (
        request.headers.get("X-Store-Identifier")
        or request.headers.get("x-store-identifier")
        or request.headers.get("X-Shopify-Shop-Domain")
        or request.headers.get("x-shopify-shop-domain")
        or request.query_params.get("store")
    )
    if not store or not str(store).strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "Missing store identifier: use path /webhook/order-created/{store_identifier}, "
                "header X-Store-Identifier, or query ?store="
            ),
        )
    return await _handle_order_webhook(str(store).strip(), request, session)


@router.post("/webhook/order-created/{store_identifier:path}")
async def receive_order_created_webhook_with_store(
    store_identifier: str,
    request: Request,
    session: AsyncSession = Depends(get_db_session),
) -> dict[str, str | int | bool | None]:
    return await _handle_order_webhook(store_identifier.strip(), request, session)
