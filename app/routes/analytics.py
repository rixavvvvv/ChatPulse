from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.analytics import (
    WorkspaceMessageAnalyticsResponse,
    WorkspaceMessageTimelineResponse,
)
from app.services.analytics_service import (
    get_workspace_message_analytics,
    get_workspace_message_timeline,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.get("/messages", response_model=WorkspaceMessageAnalyticsResponse)
async def workspace_message_analytics_route(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> WorkspaceMessageAnalyticsResponse:
    return await get_workspace_message_analytics(
        session=session,
        workspace_id=workspace.id,
    )


@router.get("/messages/timeline", response_model=WorkspaceMessageTimelineResponse)
async def workspace_message_timeline_route(
    days: int = 14,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> WorkspaceMessageTimelineResponse:
    return await get_workspace_message_timeline(
        session=session,
        workspace_id=workspace.id,
        days=days,
    )
