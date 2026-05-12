from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.contact_activities import ContactActivityResponse
from app.services.contact_activity_service import list_contact_activities

router = APIRouter(prefix="/contacts/{contact_id}/activities", tags=["Contact Activities"])


@router.get("", response_model=list[ContactActivityResponse])
async def get_contact_activity(
    contact_id: int,
    limit: int = 50,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[ContactActivityResponse]:
    rows = await list_contact_activities(
        session=session,
        workspace_id=workspace.id,
        contact_id=contact_id,
        limit=limit,
    )
    return [ContactActivityResponse.model_validate(row) for row in rows]

