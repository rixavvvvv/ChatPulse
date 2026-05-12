from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.contact_notes import ContactNoteCreateRequest, ContactNoteResponse
from app.services.contact_note_service import (
    add_contact_note,
    list_contact_notes,
    soft_delete_contact_note,
)

router = APIRouter(prefix="/contacts/{contact_id}/notes", tags=["Contact Notes"])


@router.get("", response_model=list[ContactNoteResponse])
async def get_contact_notes(
    contact_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[ContactNoteResponse]:
    rows = await list_contact_notes(
        session=session,
        workspace_id=workspace.id,
        contact_id=contact_id,
        include_deleted=False,
    )
    return [ContactNoteResponse.model_validate(row) for row in rows]


@router.post("", response_model=ContactNoteResponse, status_code=status.HTTP_201_CREATED)
async def create_contact_note(
    contact_id: int,
    payload: ContactNoteCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
) -> ContactNoteResponse:
    try:
        row = await add_contact_note(
            session=session,
            workspace_id=workspace.id,
            contact_id=contact_id,
            author_user_id=user.id,
            body=payload.body,
        )
        return ContactNoteResponse.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.delete("/{note_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact_note(
    contact_id: int,
    note_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> None:
    ok = await soft_delete_contact_note(
        session=session,
        workspace_id=workspace.id,
        contact_id=contact_id,
        note_id=note_id,
    )
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Note not found")

