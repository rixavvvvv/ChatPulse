from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.template import TemplateStatus
from app.models.workspace import Workspace
from app.schemas.bulk import (
    BulkQueueEnqueueResponse,
    BulkQueueStatusResponse,
    BulkSendRequest,
    BulkSendResponse,
)
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.bulk_service import bulk_send_messages
from app.services.queue_service import enqueue_bulk_send_job, get_scoped_job_status
from app.services.template_service import get_template_by_id, sync_template_status_from_meta

router = APIRouter(tags=["Bulk Messaging"])


async def _sync_template_for_bulk_send(
    session: AsyncSession,
    workspace: Workspace,
    template,
):
    try:
        return await sync_template_status_from_meta(
            session=session,
            workspace_id=workspace.id,
            template=template,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "Template is not available as approved on Meta for the current workspace credentials. "
                f"{exc}"
            ),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Unable to sync template status from Meta: {exc}",
        )


@router.post("/bulk-send", response_model=BulkSendResponse)
async def bulk_send(
    payload: BulkSendRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> BulkSendResponse:
    template_id = payload.template_id
    if template_id is not None:
        template = await get_template_by_id(
            session=session,
            workspace_id=workspace.id,
            template_id=template_id,
        )
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found in workspace",
            )
        template = await _sync_template_for_bulk_send(
            session=session,
            workspace=workspace,
            template=template,
        )
        if template.status != TemplateStatus.approved:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Bulk send requires an approved WhatsApp template. Sync status on the Templates page if it was just approved.",
            )
        if not template.meta_template_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Template must be submitted and synced with Meta before sending.",
            )

    return await bulk_send_messages(
        session=session,
        message_template=payload.message_template,
        contact_ids=payload.contact_ids,
        workspace_id=workspace.id,
        template_id=template_id,
    )


@router.post("/bulk-send/queue", response_model=BulkQueueEnqueueResponse)
async def bulk_send_queue(
    payload: BulkSendRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> BulkQueueEnqueueResponse:
    template_id = payload.template_id
    if template_id is not None:
        template = await get_template_by_id(
            session=session,
            workspace_id=workspace.id,
            template_id=template_id,
        )
        if not template:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Template not found in workspace",
            )
        template = await _sync_template_for_bulk_send(
            session=session,
            workspace=workspace,
            template=template,
        )
        if template.status != TemplateStatus.approved or not template.meta_template_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Queued bulk send requires an approved template synced with Meta.",
            )

    try:
        await ensure_workspace_can_send(
            session=session,
            workspace_id=workspace.id,
            requested_count=len(payload.contact_ids),
        )
        return enqueue_bulk_send_job(
            workspace_id=workspace.id,
            message_template=payload.message_template,
            contact_ids=payload.contact_ids,
            template_id=payload.template_id,
        )
    except BillingLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(exc),
        )


@router.get("/bulk-send/queue/{job_id}", response_model=BulkQueueStatusResponse)
async def bulk_send_queue_status(
    job_id: str,
    workspace: Workspace = Depends(get_current_workspace),
) -> BulkQueueStatusResponse:
    try:
        return get_scoped_job_status(job_id=job_id, workspace_id=workspace.id)
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
