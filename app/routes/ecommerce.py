from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.ecommerce import (
    EcommerceEventTemplateMapRequest,
    EcommerceEventTemplateMapResponse,
    EcommerceStoreCreateRequest,
    EcommerceStoreResponse,
)
from app.services.ecommerce_store_service import create_store_connection, list_stores_for_workspace
from app.services.ecommerce_template_map_service import list_event_maps, upsert_event_template_map

router = APIRouter(prefix="/ecommerce", tags=["Ecommerce"])


@router.post("/stores", response_model=EcommerceStoreResponse)
async def create_ecommerce_store(
    payload: EcommerceStoreCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> EcommerceStoreResponse:
    try:
        row = await create_store_connection(
            session=session,
            workspace_id=workspace.id,
            store_identifier=payload.store_identifier,
            webhook_secret=payload.webhook_secret,
            access_token=payload.access_token,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return EcommerceStoreResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        store_identifier=row.store_identifier,
        access_token_configured=bool(row.access_token_encrypted),
    )


@router.get("/stores", response_model=list[EcommerceStoreResponse])
async def list_ecommerce_stores(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[EcommerceStoreResponse]:
    rows = await list_stores_for_workspace(session, workspace_id=workspace.id)
    return [
        EcommerceStoreResponse(
            id=r.id,
            workspace_id=r.workspace_id,
            store_identifier=r.store_identifier,
            access_token_configured=bool(r.access_token_encrypted),
        )
        for r in rows
    ]


@router.put("/event-mappings", response_model=EcommerceEventTemplateMapResponse)
async def upsert_event_mapping(
    payload: EcommerceEventTemplateMapRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> EcommerceEventTemplateMapResponse:
    try:
        row = await upsert_event_template_map(
            session=session,
            workspace_id=workspace.id,
            event_type=payload.event_type,
            template_id=payload.template_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    return EcommerceEventTemplateMapResponse(
        id=row.id,
        workspace_id=row.workspace_id,
        event_type=row.event_type,
        template_id=row.template_id,
    )


@router.get("/event-mappings", response_model=list[EcommerceEventTemplateMapResponse])
async def list_event_mappings(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[EcommerceEventTemplateMapResponse]:
    rows = await list_event_maps(session, workspace_id=workspace.id)
    return [
        EcommerceEventTemplateMapResponse(
            id=r.id,
            workspace_id=r.workspace_id,
            event_type=r.event_type,
            template_id=r.template_id,
        )
        for r in rows
    ]
