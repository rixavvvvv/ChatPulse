import asyncio

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.campaign import CampaignStatus
from app.models.template import TemplateStatus
from app.models.workspace import Workspace
from app.schemas.bulk import BulkQueueStatusResponse
from app.schemas.campaign import (
    CampaignAudienceBindRequest,
    CampaignAudienceBindResponse,
    CampaignCreateRequest,
    CampaignProgressResponse,
    CampaignQueueRequest,
    CampaignQueueResponse,
    CampaignResponse,
)
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.campaign_service import (
    bind_campaign_audience_snapshot,
    count_campaign_audience,
    create_campaign,
    get_campaign_progress,
    get_campaign_by_id,
    list_campaigns,
    set_campaign_status,
)
from app.queue.tasks import run_campaign_send_inline
from app.services.queue_service import enqueue_campaign_job, get_scoped_job_status
from app.services.template_service import get_template_by_id

router = APIRouter(prefix="/campaigns", tags=["Campaigns"])


async def _build_campaign_response(
    session: AsyncSession,
    workspace: Workspace,
    campaign_id: int,
) -> CampaignResponse:
    campaign = await get_campaign_by_id(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign_id,
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    audience_count = await count_campaign_audience(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign.id,
    )

    return CampaignResponse(
        id=campaign.id,
        template_id=campaign.template_id,
        name=campaign.name,
        message_template=campaign.message_template,
        status=campaign.status,
        audience_count=audience_count,
        success_count=campaign.success_count,
        failed_count=campaign.failed_count,
        queued_job_id=campaign.queued_job_id,
        last_error=campaign.last_error,
        created_at=campaign.created_at,
        updated_at=campaign.updated_at,
    )


@router.post("", response_model=CampaignResponse, status_code=status.HTTP_201_CREATED)
async def create_campaign_route(
    payload: CampaignCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> CampaignResponse:
    template = await get_template_by_id(
        session=session,
        workspace_id=workspace.id,
        template_id=payload.template_id,
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    campaign = await create_campaign(
        session=session,
        workspace_id=workspace.id,
        template_id=payload.template_id,
        name=payload.name,
        message_template=template.body,
    )
    return await _build_campaign_response(
        session=session,
        workspace=workspace,
        campaign_id=campaign.id,
    )


@router.get("", response_model=list[CampaignResponse])
async def list_campaigns_route(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[CampaignResponse]:
    campaigns = await list_campaigns(
        session=session,
        workspace_id=workspace.id,
    )

    responses: list[CampaignResponse] = []
    for campaign in campaigns:
        audience_count = await count_campaign_audience(
            session=session,
            workspace_id=workspace.id,
            campaign_id=campaign.id,
        )
        responses.append(
            CampaignResponse(
                id=campaign.id,
                template_id=campaign.template_id,
                name=campaign.name,
                message_template=campaign.message_template,
                status=campaign.status,
                audience_count=audience_count,
                success_count=campaign.success_count,
                failed_count=campaign.failed_count,
                queued_job_id=campaign.queued_job_id,
                last_error=campaign.last_error,
                created_at=campaign.created_at,
                updated_at=campaign.updated_at,
            )
        )

    return responses


@router.get("/{campaign_id}", response_model=CampaignResponse)
async def get_campaign_route(
    campaign_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> CampaignResponse:
    return await _build_campaign_response(
        session=session,
        workspace=workspace,
        campaign_id=campaign_id,
    )


@router.post("/{campaign_id}/audience", response_model=CampaignAudienceBindResponse)
async def bind_campaign_audience_route(
    campaign_id: int,
    payload: CampaignAudienceBindRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> CampaignAudienceBindResponse:
    campaign = await get_campaign_by_id(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign_id,
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.status not in {CampaignStatus.draft, CampaignStatus.failed, CampaignStatus.completed}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Audience can be updated only when campaign is draft/completed/failed",
        )

    bound, skipped = await bind_campaign_audience_snapshot(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign.id,
        contact_ids=payload.contact_ids,
    )

    return CampaignAudienceBindResponse(
        campaign_id=campaign.id,
        audience_count=bound,
        skipped_count=skipped,
    )


@router.post("/{campaign_id}/queue", response_model=CampaignQueueResponse)
async def queue_campaign_route(
    campaign_id: int,
    payload: CampaignQueueRequest | None = None,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> CampaignQueueResponse:
    campaign = await get_campaign_by_id(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign_id,
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    audience_count = await count_campaign_audience(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign.id,
    )
    if audience_count == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Campaign audience is empty",
        )

    try:
        await ensure_workspace_can_send(
            session=session,
            workspace_id=workspace.id,
            requested_count=audience_count,
        )
    except BillingLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        )

    if campaign.status not in {CampaignStatus.draft, CampaignStatus.completed, CampaignStatus.failed}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Campaign cannot be queued from status {campaign.status}",
        )

    template = await get_template_by_id(
        session=session,
        workspace_id=workspace.id,
        template_id=campaign.template_id,
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found for campaign",
        )
    if template.status != TemplateStatus.approved:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Campaign template must be approved before queueing",
        )

    schedule_at = payload.schedule_at if payload is not None else None

    try:
        queue_result = enqueue_campaign_job(
            workspace_id=workspace.id,
            campaign_id=campaign.id,
            schedule_at=schedule_at,
        )
    except Exception as exc:
        if schedule_at is not None:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=str(exc),
            )

        # If queue broker is unavailable, run immediate send inline so users can still execute campaigns.
        try:
            await asyncio.to_thread(
                run_campaign_send_inline,
                workspace.id,
                campaign.id,
            )
            refreshed_campaign = await get_campaign_by_id(
                session=session,
                workspace_id=workspace.id,
                campaign_id=campaign.id,
            )
            if not refreshed_campaign:
                raise RuntimeError("Campaign not found after inline execution")

            return CampaignQueueResponse(
                campaign_id=refreshed_campaign.id,
                status=refreshed_campaign.status,
                job_id=f"inline:{refreshed_campaign.id}",
            )
        except Exception as inline_exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Queue broker is unavailable and inline campaign execution failed: "
                    f"{inline_exc}"
                ),
            ) from inline_exc

    try:
        campaign = await set_campaign_status(
            session=session,
            campaign=campaign,
            status=CampaignStatus.queued,
            job_id=queue_result.job_id,
            success_count=0,
            failed_count=0,
            last_error=None,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(exc),
        )

    return CampaignQueueResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        job_id=queue_result.job_id,
    )


@router.get("/{campaign_id}/queue/{job_id}", response_model=BulkQueueStatusResponse)
async def campaign_queue_status_route(
    campaign_id: int,
    job_id: str,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> BulkQueueStatusResponse:
    campaign = await get_campaign_by_id(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign_id,
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    if campaign.queued_job_id and campaign.queued_job_id != job_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="job_id does not match campaign queued job",
        )

    try:
        return get_scoped_job_status(job_id=job_id, workspace_id=workspace.id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.get("/{campaign_id}/progress", response_model=CampaignProgressResponse)
async def campaign_progress_route(
    campaign_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> CampaignProgressResponse:
    campaign = await get_campaign_by_id(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign_id,
    )
    if not campaign:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Campaign not found",
        )

    total_count, processed_count, sent_count, failed_count, skipped_count = await get_campaign_progress(
        session=session,
        workspace_id=workspace.id,
        campaign_id=campaign.id,
    )

    progress_percentage = 0.0
    if total_count > 0:
        progress_percentage = round((processed_count / total_count) * 100, 2)

    return CampaignProgressResponse(
        campaign_id=campaign.id,
        status=campaign.status,
        total_count=total_count,
        processed_count=processed_count,
        sent_count=sent_count,
        failed_count=failed_count,
        skipped_count=skipped_count,
        progress_percentage=progress_percentage,
    )
