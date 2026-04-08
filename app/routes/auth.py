from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.auth import LoginRequest, SignupRequest, TokenResponse, UserResponse
from app.services.auth_service import authenticate_user, create_access_token, hash_password
from app.services.user_service import create_user, get_user_by_email
from app.services.workspace_service import (
    build_default_workspace_name,
    create_workspace_with_owner_membership,
    get_default_workspace_id_for_user,
)

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/signup", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def signup(
    payload: SignupRequest,
    session: AsyncSession = Depends(get_db_session),
) -> UserResponse:
    existing_user = await get_user_by_email(session, payload.email)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    try:
        user = await create_user(
            session=session,
            email=payload.email,
            password_hash=hash_password(payload.password),
        )
        await create_workspace_with_owner_membership(
            session=session,
            name=build_default_workspace_name(payload.email),
            owner_id=user.id,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    return UserResponse.model_validate(user)


@router.post("/login", response_model=TokenResponse)
async def login(
    payload: LoginRequest,
    session: AsyncSession = Depends(get_db_session),
) -> TokenResponse:
    user = await authenticate_user(
        session=session,
        email=payload.email,
        password=payload.password,
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )

    workspace_id = await get_default_workspace_id_for_user(
        session=session,
        user_id=user.id,
    )

    if workspace_id is None:
        workspace = await create_workspace_with_owner_membership(
            session=session,
            name=build_default_workspace_name(user.email),
            owner_id=user.id,
        )
        workspace_id = workspace.id

    token = create_access_token(user_id=user.id, workspace_id=workspace_id)
    return TokenResponse(access_token=token, workspace_id=workspace_id)


@router.get("/me", response_model=UserResponse)
async def read_current_user(
    current_user: User = Depends(get_current_user),
    _workspace: Workspace = Depends(get_current_workspace),
) -> UserResponse:
    return UserResponse.model_validate(current_user)
