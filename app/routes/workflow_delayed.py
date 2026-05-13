from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_id
from app.models.workflow_delayed import DelayedExecutionStatus
from app.schemas.workflow_delayed import (
    DelayedExecutionCreate,
    DelayedExecutionUpdate,
    DelayedExecutionResponse,
    DelayedExecutionListResponse,
    DelayedExecutionStats,
    BusinessHoursCreate,
    BusinessHoursResponse,
)
from app.services import delayed_execution_service
from app.models.user import User

router = APIRouter(prefix="/delayed-executions", tags=["delayed-executions"])


@router.post("", response_model=DelayedExecutionResponse, status_code=status.HTTP_201_CREATED)
async def create_delayed_execution(
    execution_data: DelayedExecutionCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
    current_user: User = Depends(get_current_user),
):
    from app.services.workflow_service import get_workflow_by_id

    workflow = await get_workflow_by_id(db, execution_data.workflow_definition_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    try:
        execution = await delayed_execution_service.create_delayed_execution(
            db,
            workspace_id=workspace_id,
            workflow_definition_id=execution_data.workflow_definition_id,
            delay_type=execution_data.delay_config.delay_type.value,
            delay_config=execution_data.delay_config.config,
            context=execution_data.context,
            trigger_data=execution_data.trigger_data,
            max_retries=execution_data.max_retries,
            idempotency_key=execution_data.idempotency_key,
        )
        return execution
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))


@router.get("", response_model=list[DelayedExecutionListResponse])
async def list_delayed_executions(
    workflow_id: int | None = None,
    status_filter: DelayedExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    executions, total = await delayed_execution_service.list_delayed_executions(
        db,
        workspace_id,
        workflow_definition_id=workflow_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return executions


@router.get("/stats", response_model=DelayedExecutionStats)
async def get_delayed_execution_stats(
    workflow_id: int | None = None,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    stats = await delayed_execution_service.get_delayed_execution_stats(
        db, workspace_id, workflow_id
    )
    return stats


@router.get("/{execution_id}", response_model=DelayedExecutionResponse)
async def get_delayed_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    execution = await delayed_execution_service.get_delayed_execution(
        db, execution_id, workspace_id
    )
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


@router.patch("/{execution_id}", response_model=DelayedExecutionResponse)
async def update_delayed_execution(
    execution_id: str,
    execution_data: DelayedExecutionUpdate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    execution = await delayed_execution_service.get_delayed_execution(
        db, execution_id, workspace_id
    )
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    if execution_data.status == DelayedExecutionStatus.cancelled:
        execution = await delayed_execution_service.cancel_delayed_execution(db, execution)
    else:
        execution = await delayed_execution_service.update_delayed_execution(
            db,
            execution,
            status=execution_data.status.value if execution_data.status else None,
            scheduled_at=execution_data.scheduled_at,
            context=execution_data.context,
            max_retries=execution_data.max_retries,
        )

    return execution


@router.delete("/{execution_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_delayed_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    execution = await delayed_execution_service.get_delayed_execution(
        db, execution_id, workspace_id
    )
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")

    await delayed_execution_service.cancel_delayed_execution(db, execution)


business_hours_router = APIRouter(prefix="/business-hours", tags=["business-hours"])


@business_hours_router.post("", response_model=BusinessHoursResponse, status_code=status.HTTP_201_CREATED)
async def create_business_hours(
    config_data: BusinessHoursCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    config = await delayed_execution_service.create_business_hours(
        db,
        workspace_id=workspace_id,
        timezone=config_data.timezone,
        day_of_week=config_data.day_of_week,
        start_time=config_data.start_time,
        end_time=config_data.end_time,
        is_active=config_data.is_active,
    )
    return config


@business_hours_router.get("", response_model=list[BusinessHoursResponse])
async def list_business_hours(
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    configs = await delayed_execution_service.list_business_hours(db, workspace_id)
    return configs


@business_hours_router.delete("/{config_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_business_hours(
    config_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    await delayed_execution_service.delete_business_hours(db, config_id, workspace_id)