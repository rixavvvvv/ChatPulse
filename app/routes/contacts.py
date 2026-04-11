from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.schemas.contact import ContactCreateRequest, ContactResponse, ContactUploadResponse
from app.models.workspace import Workspace
from app.services.contact_service import create_contact, import_contacts_from_csv, list_contacts

router = APIRouter(prefix="/contacts", tags=["Contacts"])


@router.get("", response_model=list[ContactResponse])
async def get_contacts(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[ContactResponse]:
    contacts = await list_contacts(session=session, workspace_id=workspace.id)
    return [ContactResponse.model_validate(contact) for contact in contacts]


@router.post("", response_model=ContactResponse, status_code=status.HTTP_201_CREATED)
async def add_contact(
    payload: ContactCreateRequest,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> ContactResponse:
    try:
        contact = await create_contact(
            session=session,
            workspace_id=workspace.id,
            name=payload.name,
            phone=payload.phone,
            tags=payload.tags,
        )
        return ContactResponse.model_validate(contact)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )


@router.post("/upload-csv", response_model=ContactUploadResponse)
async def upload_contacts_csv(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> ContactUploadResponse:
    if not file.filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="File name is required",
        )

    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only CSV files are supported",
        )

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    try:
        return await import_contacts_from_csv(
            session=session,
            file_bytes=file_bytes,
            workspace_id=workspace.id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    finally:
        await file.close()
