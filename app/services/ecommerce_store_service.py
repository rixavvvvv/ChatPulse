from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret
from app.models.ecommerce import EcommerceStoreConnection


async def create_store_connection(
    session: AsyncSession,
    *,
    workspace_id: int,
    store_identifier: str,
    webhook_secret: str,
    access_token: str | None,
) -> EcommerceStoreConnection:
    normalized_id = store_identifier.strip()
    if not normalized_id:
        raise ValueError("store_identifier is required")

    enc_secret = encrypt_secret(webhook_secret)
    enc_token = encrypt_secret(access_token) if access_token and access_token.strip() else None

    row = EcommerceStoreConnection(
        workspace_id=workspace_id,
        store_identifier=normalized_id,
        webhook_secret_encrypted=enc_secret,
        access_token_encrypted=enc_token,
    )
    session.add(row)
    try:
        await session.commit()
    except IntegrityError as exc:
        await session.rollback()
        raise ValueError("A store with this identifier already exists") from exc
    await session.refresh(row)
    return row


async def get_store_by_identifier(
    session: AsyncSession,
    *,
    store_identifier: str,
) -> EcommerceStoreConnection | None:
    sid = store_identifier.strip()
    if not sid:
        return None
    stmt = select(EcommerceStoreConnection).where(
        EcommerceStoreConnection.store_identifier == sid,
    )
    return (await session.execute(stmt)).scalar_one_or_none()


def get_webhook_secret_plaintext(connection: EcommerceStoreConnection) -> str:
    return decrypt_secret(connection.webhook_secret_encrypted)


async def list_stores_for_workspace(
    session: AsyncSession,
    *,
    workspace_id: int,
) -> list[EcommerceStoreConnection]:
    stmt = select(EcommerceStoreConnection).where(
        EcommerceStoreConnection.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())
