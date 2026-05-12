from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.models.user import User
from app.models.workspace import Workspace
from app.schemas.contact_imports import (
    ContactImportCreateResponse,
    ContactImportJobErrorsResponse,
    ContactImportJobResponse,
    ContactImportRowErrorResponse,
)
from app.services.contact_import_service import (
    create_contact_import_job_from_csv,
    get_contact_import_job,
    list_contact_import_jobs,
    list_contact_import_row_errors,
)

router = APIRouter(prefix="/contacts/imports", tags=["Contact Imports"])


@router.post("", response_model=ContactImportCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_contact_import(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
    user: User = Depends(get_current_user),
) -> ContactImportCreateResponse:
    if not file.filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="File name is required")
    if not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only CSV files are supported")
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Uploaded file is empty")
    try:
        job = await create_contact_import_job_from_csv(
            session=session,
            workspace_id=workspace.id,
            created_by_user_id=user.id,
            original_filename=file.filename,
            file_bytes=file_bytes,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    finally:
        await file.close()

    from app.queue.tasks import process_contact_import_job_task

    async_result = process_contact_import_job_task.delay(workspace.id, job.id)
    job.celery_task_id = async_result.id
    await session.commit()
    return ContactImportCreateResponse(job_id=job.id, celery_task_id=async_result.id)


@router.get("", response_model=list[ContactImportJobResponse])
async def list_contact_imports(
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> list[ContactImportJobResponse]:
    jobs = await list_contact_import_jobs(session=session, workspace_id=workspace.id, limit=20)
    return [
        ContactImportJobResponse(
            id=j.id,
            status=j.status,
            total_rows=j.total_rows,
            processed_rows=j.processed_rows,
            inserted_rows=j.inserted_rows,
            skipped_rows=j.skipped_rows,
            failed_rows=j.failed_rows,
            error_message=j.error_message,
            created_at=j.created_at,
            completed_at=j.completed_at,
        )
        for j in jobs
    ]


@router.get("/{job_id}", response_model=ContactImportJobResponse)
async def get_contact_import(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> ContactImportJobResponse:
    job = await get_contact_import_job(session=session, workspace_id=workspace.id, job_id=job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    return ContactImportJobResponse(
        id=job.id,
        status=job.status,
        total_rows=job.total_rows,
        processed_rows=job.processed_rows,
        inserted_rows=job.inserted_rows,
        skipped_rows=job.skipped_rows,
        failed_rows=job.failed_rows,
        error_message=job.error_message,
        created_at=job.created_at,
        completed_at=job.completed_at,
    )


@router.get("/{job_id}/errors", response_model=ContactImportJobErrorsResponse)
async def get_contact_import_errors(
    job_id: int,
    session: AsyncSession = Depends(get_db_session),
    workspace: Workspace = Depends(get_current_workspace),
) -> ContactImportJobErrorsResponse:
    job = await get_contact_import_job(session=session, workspace_id=workspace.id, job_id=job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Import job not found")
    rows = await list_contact_import_row_errors(session=session, job_id=job_id, limit=200)
    return ContactImportJobErrorsResponse(
        job_id=job_id,
        errors=[
            ContactImportRowErrorResponse(
                row_number=r.row_number,
                error=r.error or "Error",
                raw=r.raw or {},
            )
            for r in rows
        ],
    )

