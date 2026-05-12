from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace, require_workspace_admin
from app.models.workspace import Workspace
from app.schemas.template import (
    TemplateCreateRequest,
    TemplateResponse,
    TemplateSubmitResponse,
    TemplateStatusUpdateRequest,
)
from app.services.template_service import (
    create_template,
    get_template_by_id,
    list_templates,
    submit_template_to_meta,
    sync_all_templates_from_meta,
    sync_template_status_from_meta,
    update_template_status,
)

router = APIRouter(prefix="/templates", tags=["Templates"])


def _to_template_response(template) -> TemplateResponse:
    return TemplateResponse(
        id=template.id,
        name=template.name,
        language=template.language,
        category=template.category,
        header_type=template.header_type,
        header_content=template.header_content,
        body_text=template.body_text,
        variables=template.variables,
        sample_values=template.body_examples,
        footer_text=template.footer_text,
        buttons=template.buttons,
        status=template.status,
        meta_template_id=template.meta_template_id,
        rejection_reason=template.rejection_reason,
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
            language=payload.language,
            category=payload.category,
            header_type=payload.header_type,
            header_content=payload.header_content,
            body_text=payload.body_text,
            variables=payload.variables,
            sample_values=payload.sample_values,
            footer_text=payload.footer_text,
            buttons=payload.buttons,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except IntegrityError:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Template name already exists in this workspace",
        )

    return _to_template_response(template)


@router.post("/{template_id}/submit", response_model=TemplateSubmitResponse)
async def submit_template_route(
    template_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> TemplateSubmitResponse:
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

    try:
        template = await submit_template_to_meta(
            session=session,
            workspace_id=workspace.id,
            template=template,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    return TemplateSubmitResponse(
        id=template.id,
        status=template.status,
        meta_template_id=template.meta_template_id,
    )


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

    if payload.status.value in {"approved", "pending"}:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Use submit/sync endpoints to update pending/approved status from Meta",
        )

    template = await update_template_status(
        session=session,
        template=template,
        status=payload.status,
    )
    return _to_template_response(template)


@router.get("/{template_id}/status", response_model=TemplateResponse)
async def sync_template_status_route(
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

    try:
        template = await sync_template_status_from_meta(
            session=session,
            workspace_id=workspace.id,
            template=template,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )

    return _to_template_response(template)


@router.post("/sync-all")
async def sync_all_templates_route(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> dict[str, int]:
    try:
        result = await sync_all_templates_from_meta(session=session, workspace_id=workspace.id)
        return {"created": int(result.get("created", 0)), "updated": int(result.get("updated", 0))}
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    except RuntimeError as exc:
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
