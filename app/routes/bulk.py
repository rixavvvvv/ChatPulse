from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
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

router = APIRouter(tags=["Bulk Messaging"])


@router.post("/bulk-send", response_model=BulkSendResponse)
async def bulk_send(
    payload: BulkSendRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> BulkSendResponse:
    return await bulk_send_messages(
        session=session,
        message_template=payload.message_template,
        contact_ids=payload.contact_ids,
        workspace_id=workspace.id,
    )


@router.post("/bulk-send/queue", response_model=BulkQueueEnqueueResponse)
async def bulk_send_queue(
    payload: BulkSendRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> BulkQueueEnqueueResponse:
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
