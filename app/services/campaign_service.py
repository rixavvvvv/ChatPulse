from collections.abc import Sequence
import hashlib

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.campaign import Campaign, CampaignStatus
from app.models.campaign_contact import (
    CampaignContact,
    CampaignContactDeliveryStatus,
)
from app.models.contact import Contact

_ALLOWED_STATUS_TRANSITIONS: dict[CampaignStatus, set[CampaignStatus]] = {
    CampaignStatus.draft: {CampaignStatus.queued},
    CampaignStatus.queued: {CampaignStatus.running, CampaignStatus.failed},
    CampaignStatus.running: {CampaignStatus.completed, CampaignStatus.failed},
    CampaignStatus.completed: {CampaignStatus.queued},
    CampaignStatus.failed: {CampaignStatus.queued},
}


def render_campaign_message_template(
    template: str,
    name: str,
    phone: str,
) -> str:
    rendered = template.replace("{{name}}", name)
    rendered = rendered.replace("{{ phone }}", phone)
    rendered = rendered.replace("{{phone}}", phone)
    return rendered


async def create_campaign(
    session: AsyncSession,
    workspace_id: int,
    template_id: int,
    name: str,
    message_template: str,
) -> Campaign:
    campaign = Campaign(
        workspace_id=workspace_id,
        template_id=template_id,
        name=name,
        message_template=message_template,
        status=CampaignStatus.draft,
        success_count=0,
        failed_count=0,
        last_error=None,
        queued_job_id=None,
    )
    session.add(campaign)
    await session.commit()
    await session.refresh(campaign)
    return campaign


async def get_campaign_by_id(
    session: AsyncSession,
    workspace_id: int,
    campaign_id: int,
) -> Campaign | None:
    stmt = select(Campaign).where(
        Campaign.id == campaign_id,
        Campaign.workspace_id == workspace_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def list_campaigns(
    session: AsyncSession,
    workspace_id: int,
) -> list[Campaign]:
    stmt = (
        select(Campaign)
        .where(Campaign.workspace_id == workspace_id)
        .order_by(Campaign.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def count_campaign_audience(
    session: AsyncSession,
    workspace_id: int,
    campaign_id: int,
) -> int:
    stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
    )
    result = await session.execute(stmt)
    return int(result.scalar_one())


async def bind_campaign_audience_snapshot(
    session: AsyncSession,
    workspace_id: int,
    campaign_id: int,
    contact_ids: Sequence[int],
) -> tuple[int, int]:
    if not contact_ids:
        return 0, 0

    contacts_stmt = select(Contact).where(
        Contact.workspace_id == workspace_id,
        Contact.id.in_(contact_ids),
    )
    contacts_result = await session.execute(contacts_stmt)
    contacts_by_id = {
        contact.id: contact for contact in contacts_result.scalars().all()}

    await session.execute(
        delete(CampaignContact).where(
            CampaignContact.workspace_id == workspace_id,
            CampaignContact.campaign_id == campaign_id,
        )
    )

    seen_phones: set[str] = set()
    bound = 0
    skipped = 0

    for contact_id in contact_ids:
        contact = contacts_by_id.get(contact_id)
        if not contact:
            skipped += 1
            continue

        if contact.phone in seen_phones:
            skipped += 1
            continue

        seen_phones.add(contact.phone)
        idempotency_key = hashlib.sha256(
            f"{workspace_id}:{campaign_id}:{contact.phone}".encode("utf-8")
        ).hexdigest()
        session.add(
            CampaignContact(
                workspace_id=workspace_id,
                campaign_id=campaign_id,
                source_contact_id=contact.id,
                idempotency_key=idempotency_key,
                name=contact.name,
                phone=contact.phone,
                delivery_status=CampaignContactDeliveryStatus.pending,
                attempt_count=0,
                failure_classification=None,
                last_error=None,
            )
        )
        bound += 1

    await session.commit()
    return bound, skipped


async def set_campaign_status(
    session: AsyncSession,
    campaign: Campaign,
    status: CampaignStatus,
    *,
    job_id: str | None = None,
    last_error: str | None = None,
    success_count: int | None = None,
    failed_count: int | None = None,
) -> Campaign:
    if campaign.status != status:
        allowed_next = _ALLOWED_STATUS_TRANSITIONS.get(campaign.status, set())
        if status not in allowed_next:
            raise ValueError(
                f"Invalid campaign status transition: {campaign.status} -> {status}"
            )

    campaign.status = status
    if job_id is not None:
        campaign.queued_job_id = job_id
    if last_error is not None:
        campaign.last_error = last_error
    elif status in {CampaignStatus.queued, CampaignStatus.running, CampaignStatus.completed}:
        campaign.last_error = None
    if success_count is not None:
        campaign.success_count = success_count
    if failed_count is not None:
        campaign.failed_count = failed_count

    await session.commit()
    await session.refresh(campaign)
    return campaign


async def get_campaign_progress(
    session: AsyncSession,
    *,
    workspace_id: int,
    campaign_id: int,
) -> tuple[int, int, int, int, int]:
    total_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
    )
    total_count = int((await session.execute(total_stmt)).scalar_one())

    sent_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.delivery_status == CampaignContactDeliveryStatus.sent,
    )
    sent_count = int((await session.execute(sent_stmt)).scalar_one())

    failed_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.delivery_status == CampaignContactDeliveryStatus.failed,
    )
    failed_count = int((await session.execute(failed_stmt)).scalar_one())

    skipped_stmt = select(func.count(CampaignContact.id)).where(
        CampaignContact.workspace_id == workspace_id,
        CampaignContact.campaign_id == campaign_id,
        CampaignContact.delivery_status == CampaignContactDeliveryStatus.skipped,
    )
    skipped_count = int((await session.execute(skipped_stmt)).scalar_one())

    processed_count = sent_count + failed_count + skipped_count
    return total_count, processed_count, sent_count, failed_count, skipped_count
