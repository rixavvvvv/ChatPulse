from dataclasses import dataclass
from urllib.parse import urlparse

import httpx
from sqlalchemy import select
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


async def upsert_workspace_meta_credential(
    session: AsyncSession,
    workspace_id: int,
    phone_number_id: str,
    access_token: str,
    business_account_id: str,
) -> MetaCredential:
    stmt = select(MetaCredential).where(
        MetaCredential.workspace_id == workspace_id)
    existing = (await session.execute(stmt)).scalar_one_or_none()

    encrypted_access_token = encrypt_secret(access_token)

    if existing:
        existing.phone_number_id = phone_number_id
        existing.access_token = encrypted_access_token
        existing.business_account_id = business_account_id
        await session.commit()
        await session.refresh(existing)
        return existing

    credential = MetaCredential(
        workspace_id=workspace_id,
        phone_number_id=phone_number_id,
        access_token=encrypted_access_token,
        business_account_id=business_account_id,
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
        )


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
        raise RuntimeError("Meta API timeout while fetching subscribed apps") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Meta API transport error while fetching subscribed apps") from exc

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
        raise RuntimeError("Meta API transport error while subscribing app") from exc

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
