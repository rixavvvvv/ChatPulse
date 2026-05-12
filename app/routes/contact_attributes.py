from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace, require_workspace_admin
from app.models.workspace import Workspace
from app.schemas.attributes import (
    AttributeDefinitionCreateRequest,
    AttributeDefinitionResponse,
    ContactAttributeUpsertRequest,
    ContactAttributeValueResponse,
)
from app.services.contact_attribute_service import (
    create_attribute_definition,
    get_attribute_definition_by_key,
    list_attribute_definitions,
    list_contact_attributes,
    upsert_contact_attribute,
)

router = APIRouter(tags=["Contact Attributes"])


@router.get("/attributes/definitions", response_model=list[AttributeDefinitionResponse])
async def get_attribute_definitions(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[AttributeDefinitionResponse]:
    rows = await list_attribute_definitions(session=session, workspace_id=workspace.id)
    return [AttributeDefinitionResponse.model_validate(row) for row in rows]


@router.post(
    "/attributes/definitions",
    response_model=AttributeDefinitionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_attribute_definition(
    payload: AttributeDefinitionCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(require_workspace_admin),
) -> AttributeDefinitionResponse:
    try:
        row = await create_attribute_definition(
            session=session,
            workspace_id=workspace.id,
            key=payload.key,
            label=payload.label,
            type=payload.type,
            is_indexed=payload.is_indexed,
        )
        return AttributeDefinitionResponse.model_validate(row)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get(
    "/contacts/{contact_id}/attributes", response_model=list[ContactAttributeValueResponse]
)
async def get_contact_attributes(
    contact_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[ContactAttributeValueResponse]:
    pairs = await list_contact_attributes(
        session=session, workspace_id=workspace.id, contact_id=contact_id
    )
    out: list[ContactAttributeValueResponse] = []
    for definition, value in pairs:
        out.append(
            ContactAttributeValueResponse(
                attribute_definition_id=definition.id,
                key=definition.key,
                type=definition.type,
                value_text=value.value_text,
                value_number=value.value_number,
                value_bool=value.value_bool,
                value_date_iso=value.value_date.isoformat() if value.value_date else None,
                updated_at=value.updated_at,
            )
        )
    return out


@router.put(
    "/contacts/{contact_id}/attributes",
    response_model=ContactAttributeValueResponse,
)
async def upsert_contact_attribute_value(
    contact_id: int,
    payload: ContactAttributeUpsertRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> ContactAttributeValueResponse:
    definition = await get_attribute_definition_by_key(
        session=session, workspace_id=workspace.id, key=payload.key
    )
    if not definition:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Attribute definition not found",
        )
    try:
        value = await upsert_contact_attribute(
            session=session,
            workspace_id=workspace.id,
            contact_id=contact_id,
            definition=definition,
            value_text=payload.value_text,
            value_number=payload.value_number,
            value_bool=payload.value_bool,
            value_date_iso=payload.value_date_iso,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return ContactAttributeValueResponse(
        attribute_definition_id=definition.id,
        key=definition.key,
        type=definition.type,
        value_text=value.value_text,
        value_number=value.value_number,
        value_bool=value.value_bool,
        value_date_iso=value.value_date.isoformat() if value.value_date else None,
        updated_at=value.updated_at,
    )

