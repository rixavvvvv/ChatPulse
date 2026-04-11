from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace, require_workspace_admin
from app.models.workspace import Workspace
from app.schemas.template import (
    TemplateCreateRequest,
    TemplateResponse,
    TemplateStatusUpdateRequest,
)
from app.services.template_service import (
    create_template,
    get_template_by_id,
    list_templates,
    update_template_status,
)

router = APIRouter(prefix="/templates", tags=["Templates"])


def _to_template_response(template) -> TemplateResponse:
    return TemplateResponse(
        id=template.id,
        name=template.name,
        body=template.body,
        variables=template.variables,
        status=template.status,
        created_at=template.created_at,
        updated_at=template.updated_at,
    )


@router.post("", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template_route(
    payload: TemplateCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> TemplateResponse:
    try:
        template = await create_template(
            session=session,
            workspace_id=workspace.id,
            name=payload.name,
            body=payload.body,
            variables=payload.variables,
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template name already exists in this workspace",
        )

    return _to_template_response(template)


@router.get("", response_model=list[TemplateResponse])
async def list_templates_route(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[TemplateResponse]:
    templates = await list_templates(session=session, workspace_id=workspace.id)
    return [_to_template_response(template) for template in templates]


@router.get("/{template_id}", response_model=TemplateResponse)
async def get_template_route(
    template_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> TemplateResponse:
    template = await get_template_by_id(
        session=session,
        workspace_id=workspace.id,
        template_id=template_id,
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    return _to_template_response(template)


@router.patch("/{template_id}/status", response_model=TemplateResponse)
async def update_template_status_route(
    template_id: int,
    payload: TemplateStatusUpdateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> TemplateResponse:
    template = await get_template_by_id(
        session=session,
        workspace_id=workspace.id,
        template_id=template_id,
    )
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Template not found",
        )

    template = await update_template_status(
        session=session,
        template=template,
        status=payload.status,
    )
    return _to_template_response(template)
