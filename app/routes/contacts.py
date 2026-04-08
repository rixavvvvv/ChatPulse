from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.schemas.contact import ContactUploadResponse
from app.models.workspace import Workspace
from app.services.contact_service import import_contacts_from_csv

router = APIRouter(prefix="/contacts", tags=["Contacts"])


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
