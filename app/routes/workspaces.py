from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.models.membership import MembershipRole
from app.models.user import User
from app.schemas.auth import TokenResponse
from app.schemas.workspace import WorkspaceCreateRequest, WorkspaceResponse, WorkspaceSwitchRequest
from app.services.auth_service import create_access_token
from app.services.workspace_service import (
    create_workspace_with_owner_membership,
    get_user_membership,
    list_user_workspaces,
)

router = APIRouter(prefix="/workspaces", tags=["Workspaces"])


@router.post("", response_model=WorkspaceResponse, status_code=status.HTTP_201_CREATED)
async def create_workspace(
    payload: WorkspaceCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> WorkspaceResponse:
    try:
        workspace = await create_workspace_with_owner_membership(
            session=session,
            name=payload.name,
            owner_id=current_user.id,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unable to create workspace",
        )

    return WorkspaceResponse(
        id=workspace.id,
        name=workspace.name,
        owner_id=workspace.owner_id,
        role=MembershipRole.admin,
        created_at=workspace.created_at,
    )


@router.get("", response_model=list[WorkspaceResponse])
async def get_my_workspaces(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> list[WorkspaceResponse]:
    rows = await list_user_workspaces(session=session, user_id=current_user.id)
    return [
        WorkspaceResponse(
            id=workspace.id,
            name=workspace.name,
            owner_id=workspace.owner_id,
            role=role,
            created_at=workspace.created_at,
        )
        for workspace, role in rows
    ]


@router.post("/switch", response_model=TokenResponse)
async def switch_workspace(
    payload: WorkspaceSwitchRequest,
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
) -> TokenResponse:
    membership = await get_user_membership(
        session=session,
        user_id=current_user.id,
        workspace_id=payload.workspace_id,
    )
    if not membership:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No access to requested workspace",
        )

    token = create_access_token(
        user_id=current_user.id,
        workspace_id=payload.workspace_id,
    )
    return TokenResponse(access_token=token, workspace_id=payload.workspace_id)
