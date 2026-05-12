from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace, require_workspace_admin
from app.models.workspace import Workspace
from app.schemas.segments import (
    SegmentCreateRequest,
    SegmentMaterializeResponse,
    SegmentPreviewRequest,
    SegmentPreviewResponse,
    SegmentResponse,
)
from app.services.segment_service import (
    create_segment,
    get_segment,
    list_segments,
    preview_segment_count,
)

router = APIRouter(prefix="/segments", tags=["Segments"])


@router.get("", response_model=list[SegmentResponse])
async def get_segments(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[SegmentResponse]:
    rows = await list_segments(session=session, workspace_id=workspace.id)
    return [SegmentResponse.model_validate(r) for r in rows]


@router.post("", response_model=SegmentResponse, status_code=status.HTTP_201_CREATED)
async def add_segment(
    payload: SegmentCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> SegmentResponse:
    try:
        row = await create_segment(
            session=session,
            workspace_id=workspace.id,
            name=payload.name,
            definition=payload.definition,
        )
        return SegmentResponse.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/preview", response_model=SegmentPreviewResponse)
async def preview_segment(
    payload: SegmentPreviewRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> SegmentPreviewResponse:
    try:
        count = await preview_segment_count(
            session=session,
            workspace_id=workspace.id,
            definition=payload.definition,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return SegmentPreviewResponse(estimated_count=count)


@router.post("/{segment_id}/materialize", response_model=SegmentMaterializeResponse)
async def materialize_segment(
    segment_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> SegmentMaterializeResponse:
    row = await get_segment(session=session, workspace_id=workspace.id, segment_id=segment_id)
    if not row:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Segment not found")

    from app.queue.tasks import process_segment_materialize_task

    async_result = process_segment_materialize_task.delay(workspace.id, segment_id)
    return SegmentMaterializeResponse(segment_id=segment_id, celery_task_id=async_result.id)

