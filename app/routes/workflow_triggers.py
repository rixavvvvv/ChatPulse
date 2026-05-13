from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_id
from app.models.workflow_trigger import TriggerExecutionStatus, TriggerSource, TriggerStatus
from app.schemas.workflow_trigger import (
    WorkflowTriggerCreate,
    WorkflowTriggerUpdate,
    WorkflowTriggerResponse,
    WorkflowTriggerWithWorkflow,
    TriggerExecutionResponse,
    TriggerStats,
    WorkflowTriggerStats,
)
from app.services import trigger_service
from app.models.user import User

router = APIRouter(prefix="/triggers", tags=["triggers"])


@router.post("/workflows/{workflow_id}/triggers", response_model=WorkflowTriggerResponse, status_code=status.HTTP_201_CREATED)
async def create_trigger(
    workflow_id: int,
    trigger_data: WorkflowTriggerCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
    current_user: User = Depends(get_current_user),
):
    from app.services.workflow_service import get_workflow_by_id

    workflow = await get_workflow_by_id(db, workflow_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    filters = [
        {
            "filter_type": f.filter_type.value,
            "field": f.field,
            "operator": f.operator.value,
            "value": f.value,
        }
        for f in trigger_data.filters
    ]

    trigger = await trigger_service.create_trigger(
        db,
        workspace_id=workspace_id,
        workflow_definition_id=workflow_id,
        name=trigger_data.name,
        description=trigger_data.description,
        source=trigger_data.source.value,
        filters=filters,
        priority=trigger_data.priority,
        created_by=current_user.id,
    )

    return trigger


@router.get("/workflows/{workflow_id}/triggers", response_model=list[WorkflowTriggerResponse])
async def list_workflow_triggers(
    workflow_id: int,
    source: TriggerSource | None = None,
    status_filter: TriggerStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    triggers, total = await trigger_service.list_triggers(
        db,
        workspace_id,
        workflow_definition_id=workflow_id,
        source=source.value if source else None,
        status=status_filter.value if status_filter else None,
        limit=limit,
        offset=offset,
    )
    return triggers


@router.get("", response_model=list[WorkflowTriggerWithWorkflow])
async def list_triggers(
    source: TriggerSource | None = None,
    status_filter: TriggerStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    triggers, total = await trigger_service.list_triggers(
        db,
        workspace_id,
        source=source.value if source else None,
        status=status_filter.value if status_filter else None,
        limit=limit,
        offset=offset,
    )

    result = []
    for trigger in triggers:
        from sqlalchemy import select
        from app.models.workflow import WorkflowDefinition
        stmt = select(WorkflowDefinition.name).where(WorkflowDefinition.id == trigger.workflow_definition_id)
        res = await db.execute(stmt)
        workflow_name = res.scalar_one_or_none()

        result.append(WorkflowTriggerWithWorkflow(
            id=trigger.id,
            workspace_id=trigger.workspace_id,
            workflow_definition_id=trigger.workflow_definition_id,
            workflow_name=workflow_name,
            name=trigger.name,
            description=trigger.description,
            source=trigger.source,
            status=trigger.status,
            filters=trigger.filters,
            priority=trigger.priority,
            created_at=trigger.created_at,
        ))

    return result


@router.get("/stats", response_model=WorkflowTriggerStats)
async def get_trigger_stats(
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    stats = await trigger_service.get_workflow_trigger_stats(db, workspace_id)
    return stats


@router.get("/{trigger_id}", response_model=WorkflowTriggerResponse)
async def get_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    trigger = await trigger_service.get_trigger_by_id(db, trigger_id, workspace_id)
    if not trigger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")
    return trigger


@router.patch("/{trigger_id}", response_model=WorkflowTriggerResponse)
async def update_trigger(
    trigger_id: int,
    trigger_data: WorkflowTriggerUpdate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    trigger = await trigger_service.get_trigger_by_id(db, trigger_id, workspace_id)
    if not trigger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")

    filters = None
    if trigger_data.filters is not None:
        filters = [
            {
                "filter_type": f.filter_type.value,
                "field": f.field,
                "operator": f.operator.value,
                "value": f.value,
            }
            for f in trigger_data.filters
        ]

    updated_trigger = await trigger_service.update_trigger(
        db,
        trigger,
        name=trigger_data.name,
        description=trigger_data.description,
        status=trigger_data.status.value if trigger_data.status else None,
        filters=filters,
        priority=trigger_data.priority,
    )

    return updated_trigger


@router.delete("/{trigger_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_trigger(
    trigger_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    trigger = await trigger_service.get_trigger_by_id(db, trigger_id, workspace_id)
    if not trigger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")

    await trigger_service.delete_trigger(db, trigger)


@router.get("/executions", response_model=list[TriggerExecutionResponse])
async def list_trigger_executions(
    trigger_id: int | None = None,
    status_filter: TriggerExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    executions, total = await trigger_service.list_trigger_executions(
        db,
        workspace_id,
        trigger_id=trigger_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return executions


@router.get("/executions/{execution_id}", response_model=TriggerExecutionResponse)
async def get_trigger_execution(
    execution_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    execution = await trigger_service.get_trigger_execution(db, execution_id, workspace_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


@router.get("/{trigger_id}/stats", response_model=TriggerStats)
async def get_single_trigger_stats(
    trigger_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    trigger = await trigger_service.get_trigger_by_id(db, trigger_id, workspace_id)
    if not trigger:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Trigger not found")

    stats = await trigger_service.get_trigger_stats(db, workspace_id, trigger_id)
    return TriggerStats(
        trigger_id=trigger_id,
        workspace_id=workspace_id,
        source=trigger.source,
        triggered_count=stats.get("total_executions", 0),
        matched_count=stats.get("total_executions", 0),
        executed_count=stats.get("completed", 0),
        failed_count=stats.get("failed", 0),
        skipped_duplicate_count=stats.get("skipped_duplicate", 0),
        avg_latency_ms=stats.get("avg_latency_ms"),
        last_triggered_at=None,
    )