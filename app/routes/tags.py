from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace, require_workspace_admin
from app.models.workspace import Workspace
from app.schemas.tags import TagCreateRequest, TagResponse
from app.services.tag_service import create_tag, list_tags

router = APIRouter(prefix="/tags", tags=["Tags"])


@router.get("", response_model=list[TagResponse])
async def get_tags(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[TagResponse]:
    rows = await list_tags(session=session, workspace_id=workspace.id)
    return [TagResponse.model_validate(row) for row in rows]


@router.post("", response_model=TagResponse, status_code=status.HTTP_201_CREATED)
async def add_tag(
    payload: TagCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> TagResponse:
    try:
        row = await create_tag(
            session=session,
            workspace_id=workspace.id,
            name=payload.name,
            color=payload.color,
        )
        return TagResponse.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

