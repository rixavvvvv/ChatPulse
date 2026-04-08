from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_secret, encrypt_secret
from app.db import AsyncSessionLocal
from app.models.meta_credential import MetaCredential


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
