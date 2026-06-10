from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.security import decrypt_secret, encrypt_secret
from app.db import AsyncSessionLocal
from app.models.meta_credential import MetaCredential

settings = get_settings()




@dataclass(frozen=True)
class WorkspaceMetaCredentials:
    phone_number_id: str
    access_token: str
    business_account_id: str
    app_secret: str | None = None
    webhook_verify_token: str | None = None


async def upsert_workspace_meta_credential(
    session: AsyncSession,
    workspace_id: int,
    phone_number_id: str,
    access_token: str,
    business_account_id: str,
    app_secret: str | None = None,
    webhook_verify_token: str | None = None,
) -> MetaCredential:

    stmt = select(MetaCredential).where(
        MetaCredential.workspace_id == workspace_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()

    encrypted_access_token = encrypt_secret(access_token)
    encrypted_app_secret = encrypt_secret(app_secret) if app_secret else None
    encrypted_webhook_token = (
        encrypt_secret(webhook_verify_token) if webhook_verify_token else None
    )

    if existing:
        existing.phone_number_id = phone_number_id
        existing.access_token = encrypted_access_token
        existing.business_account_id = business_account_id
        if encrypted_app_secret is not None:
            existing.app_secret = encrypted_app_secret
        if encrypted_webhook_token is not None:
            existing.webhook_verify_token = encrypted_webhook_token
        await session.commit()
        await session.refresh(existing)
        return existing

    credential = MetaCredential(
        workspace_id=workspace_id,
        phone_number_id=phone_number_id,
        access_token=encrypted_access_token,
        business_account_id=business_account_id,
        app_secret=encrypted_app_secret,
        webhook_verify_token=encrypted_webhook_token,
    )
    session.add(credential)
    await session.commit()
    await session.refresh(credential)
    return credential


async def get_workspace_meta_credential_summary(
    session: AsyncSession,
    workspace_id: int,
) -> MetaCredential | None:

    stmt = select(MetaCredential).where(
        MetaCredential.workspace_id == workspace_id)
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def get_workspace_meta_credentials(
    workspace_id: int,
) -> WorkspaceMetaCredentials | None:
    async with AsyncSessionLocal() as session:

        stmt = select(MetaCredential).where(
            MetaCredential.workspace_id == workspace_id)
        record = (await session.execute(stmt)).scalar_one_or_none()

        if not record:
            return None

        return WorkspaceMetaCredentials(
            phone_number_id=record.phone_number_id,
            access_token=decrypt_secret(record.access_token),
            business_account_id=record.business_account_id,
            app_secret=(decrypt_secret(record.app_secret)
                        if record.app_secret else None),
            webhook_verify_token=(
                decrypt_secret(record.webhook_verify_token)
                if record.webhook_verify_token
                else None
            ),
        )


async def get_workspace_meta_credential_flags(
    session: AsyncSession,
    workspace_id: int,
) -> dict[str, bool | str | None]:

    stmt = select(MetaCredential).where(
        MetaCredential.workspace_id == workspace_id)
    record = (await session.execute(stmt)).scalar_one_or_none()
    if not record:
        return {
            "access_token_last4": None,
            "app_secret_configured": False,
            "webhook_verify_token_configured": False,
        }

    token_last4 = None
    try:
        token_last4 = decrypt_secret(record.access_token)[-4:]
    except Exception:
        token_last4 = None

    return {
        "access_token_last4": token_last4,
        "app_secret_configured": bool(record.app_secret),
        "webhook_verify_token_configured": bool(record.webhook_verify_token),
    }


async def clear_workspace_meta_credentials(
    session: AsyncSession,
    workspace_id: int,
) -> None:

    stmt = select(MetaCredential).where(
        MetaCredential.workspace_id == workspace_id)
    record = (await session.execute(stmt)).scalar_one_or_none()
    if not record:
        return
    await session.delete(record)
    await session.commit()


async def list_all_webhook_verify_tokens(
    session: AsyncSession,
) -> list[str]:

    stmt = select(MetaCredential.webhook_verify_token).where(
        MetaCredential.webhook_verify_token.isnot(None)
    )
    rows = (await session.execute(stmt)).scalars().all()
    tokens: list[str] = []
    for raw in rows:
        if not raw:
            continue
        try:
            tokens.append(decrypt_secret(raw))
        except Exception:
            continue
    return tokens


async def list_all_app_secrets(
    session: AsyncSession,
) -> list[str]:

    stmt = select(MetaCredential.app_secret).where(
        MetaCredential.app_secret.isnot(None)
    )
    rows = (await session.execute(stmt)).scalars().all()
    secrets: list[str] = []
    for raw in rows:
        if not raw:
            continue
        try:
            secrets.append(decrypt_secret(raw))
        except Exception:
            continue
    return secrets


async def fetch_waba_info(
    *,
    access_token: str,
    business_account_id: str,
) -> dict:
    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/"
        f"{business_account_id}"
    )
    params = {
        "fields": "id,name,account_review_status,health_status,ownership_type,message_template_namespace",
    }
    return await _graph_get(url=url, access_token=access_token, params=params)


async def fetch_phone_numbers(
    *,
    access_token: str,
    business_account_id: str,
) -> list[dict]:
    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/"
        f"{business_account_id}/phone_numbers"
    )
    params = {
        "fields": "id,display_phone_number,verified_name,quality_rating,status,code_verification_status,platform_type,throughput",
        "limit": 50,
    }
    payload = await _graph_get(url=url, access_token=access_token, params=params)
    data = payload.get("data")
    return data if isinstance(data, list) else []


async def fetch_token_status(*, access_token: str) -> dict:
    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/me"
    )
    params = {"fields": "id,name"}
    return await _graph_get(url=url, access_token=access_token, params=params)


async def _graph_get(*, url: str, access_token: str, params: dict | None = None) -> dict:
    try:
        async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
                params=params,
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Meta API timeout") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Meta API transport error") from exc

    payload: dict = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            payload = parsed
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        detail = "Meta API request failed"
        error_block = payload.get("error")
        if isinstance(error_block, dict):
            message = error_block.get("message")
            if isinstance(message, str) and message.strip():
                detail = message
        raise ValueError(detail)

    return payload


async def get_waba_subscribed_apps(
    *,
    access_token: str,
    business_account_id: str,
) -> list[dict]:
    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/"
        f"{business_account_id}/subscribed_apps"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError(
            "Meta API timeout while fetching subscribed apps") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Meta API transport error while fetching subscribed apps") from exc

    payload: dict = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            payload = parsed
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        detail = "Unable to fetch subscribed apps"
        error_block = payload.get("error")
        if isinstance(error_block, dict):
            message = error_block.get("message")
            if isinstance(message, str) and message.strip():
                detail = message
        raise ValueError(detail)

    data = payload.get("data")
    return data if isinstance(data, list) else []


async def ensure_waba_app_subscription(
    *,
    access_token: str,
    business_account_id: str,
) -> list[dict]:
    existing = await get_waba_subscribed_apps(
        access_token=access_token,
        business_account_id=business_account_id,
    )
    if existing:
        return existing

    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/"
        f"{business_account_id}/subscribed_apps"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {access_token}"},
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Meta API timeout while subscribing app") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError(
            "Meta API transport error while subscribing app") from exc

    payload: dict = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            payload = parsed
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        detail = "Unable to subscribe app to WABA"
        error_block = payload.get("error")
        if isinstance(error_block, dict):
            message = error_block.get("message")
            if isinstance(message, str) and message.strip():
                detail = message
        raise ValueError(detail)

    return await get_waba_subscribed_apps(
        access_token=access_token,
        business_account_id=business_account_id,
    )


def get_subscribed_app_links(subscribed_apps: list[dict]) -> list[str]:
    links: list[str] = []
    for item in subscribed_apps:
        if not isinstance(item, dict):
            continue
        waba_data = item.get("whatsapp_business_api_data")
        if not isinstance(waba_data, dict):
            continue
        link = waba_data.get("link")
        if isinstance(link, str) and link.strip():
            links.append(link.strip())
    return links


def has_matching_callback_host(
    *,
    subscribed_apps: list[dict],
    public_base_url: str | None,
) -> bool:
    if not public_base_url:
        return True

    target_host = urlparse(public_base_url).hostname
    if not target_host:
        return False

    for link in get_subscribed_app_links(subscribed_apps):
        if urlparse(link).hostname == target_host:
            return True

    return False
