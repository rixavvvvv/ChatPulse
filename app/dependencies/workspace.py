from fastapi import Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user, oauth2_scheme
from app.models.membership import Membership
from app.models.user import User
from app.models.workspace import Workspace
from app.services.auth_service import decode_access_token


async def get_current_workspace(
    session: AsyncSession = Depends(get_db_session),
    current_user: User = Depends(get_current_user),
    token: str = Depends(oauth2_scheme),
) -> Workspace:
    unauthorized_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate workspace context",
        headers={"WWW-Authenticate": "Bearer"},
    )
    forbidden_error = HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="No access to workspace",
    )

    try:
        payload = decode_access_token(token)
        workspace_id = int(payload.get("workspace_id"))
    except (TypeError, ValueError):
        raise unauthorized_error

    membership_stmt = select(Membership).where(
        Membership.user_id == current_user.id,
        Membership.workspace_id == workspace_id,
    )
    membership = (await session.execute(membership_stmt)).scalar_one_or_none()
    if not membership:
        raise forbidden_error

    workspace = await session.get(Workspace, workspace_id)
    if not workspace:
        raise forbidden_error

    return workspace
