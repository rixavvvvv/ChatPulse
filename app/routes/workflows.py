from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.dependencies import get_db_session
from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_id
from app.models.workflow import WorkflowStatus, ExecutionStatus
from app.models.user import User
from app.schemas.workflow import (
    WorkflowDefinitionCreate,
    WorkflowDefinitionUpdate,
    WorkflowDefinitionResponse,
    WorkflowListResponse,
    WorkflowExecutionCreate,
    WorkflowExecutionResponse,
    WorkflowExecutionDetailResponse,
    WorkflowStats,
    TriggerWorkflowRequest,
)
from app.services import workflow_service
from app.services.workflow_engine import start_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])


@router.post("", response_model=WorkflowDefinitionResponse, status_code=status.HTTP_201_CREATED)
async def create_workflow(
    workflow_data: WorkflowDefinitionCreate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
    current_user=Depends(get_current_user),
):
    nodes = [
        {
            "node_id": node.node_id,
            "node_type": node.node_type.value,
            "name": node.name,
            "config": node.config,
            "position": {"x": node.position.x, "y": node.position.y},
        }
        for node in workflow_data.nodes
    ]

    edges = [
        {
            "edge_id": edge.edge_id,
            "source_node_id": edge.source_node_id,
            "target_node_id": edge.target_node_id,
            "condition": edge.condition,
        }
        for edge in workflow_data.edges
    ]

    workflow = await workflow_service.create_workflow(
        db,
        workspace_id=workspace_id,
        name=workflow_data.name,
        description=workflow_data.description,
        nodes=nodes,
        edges=edges,
        created_by=current_user.id,
    )

    return await workflow_service.get_workflow_by_id(db, workflow.id, workspace_id)


@router.get("", response_model=list[WorkflowListResponse])
async def list_workflows(
    status_filter: WorkflowStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    workflows, total = await workflow_service.list_workflows(
        db,
        workspace_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return workflows


@router.get("/{workflow_id}", response_model=WorkflowDefinitionResponse)
async def get_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    workflow = await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")
    return workflow


@router.patch("/{workflow_id}", response_model=WorkflowDefinitionResponse)
async def update_workflow(
    workflow_id: int,
    workflow_data: WorkflowDefinitionUpdate,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    workflow = await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    nodes = None
    edges = None
    if workflow_data.nodes is not None:
        nodes = [
            {
                "node_id": node.node_id,
                "node_type": node.node_type.value,
                "name": node.name,
                "config": node.config,
                "position": {"x": node.position.x, "y": node.position.y},
            }
            for node in workflow_data.nodes
        ]

    if workflow_data.edges is not None:
        edges = [
            {
                "edge_id": edge.edge_id,
                "source_node_id": edge.source_node_id,
                "target_node_id": edge.target_node_id,
                "condition": edge.condition,
            }
            for edge in workflow_data.edges
        ]

    updated_workflow = await workflow_service.update_workflow(
        db,
        workflow,
        name=workflow_data.name,
        description=workflow_data.description,
        status=workflow_data.status,
        nodes=nodes,
        edges=edges,
    )

    return await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)


@router.delete("/{workflow_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_workflow(
    workflow_id: int,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    workflow = await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    await workflow_service.delete_workflow(db, workflow)


@router.post("/{workflow_id}/trigger", response_model=WorkflowExecutionResponse, status_code=status.HTTP_201_CREATED)
async def trigger_workflow(
    workflow_id: int,
    trigger_data: TriggerWorkflowRequest,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    workflow = await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    if workflow.status != WorkflowStatus.published:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Workflow must be published to trigger")

    execution = await start_workflow(db, workflow, trigger_data.trigger_data)
    return execution


@router.get("/{workflow_id}/executions", response_model=list[WorkflowExecutionResponse])
async def list_workflow_executions(
    workflow_id: int,
    status_filter: ExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    workflow = await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)
    if not workflow:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow not found")

    executions, total = await workflow_service.list_executions(
        db,
        workspace_id,
        workflow_definition_id=workflow_id,
        status=status_filter,
        limit=limit,
        offset=offset,
    )
    return executions


@router.get("/executions/{execution_id}", response_model=WorkflowExecutionDetailResponse)
async def get_execution(
    execution_id: str,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    execution = await workflow_service.get_execution(db, execution_id, workspace_id)
    if not execution:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Execution not found")
    return execution


@router.get("/stats", response_model=WorkflowStats)
async def get_workflow_stats(
    workflow_id: int | None = None,
    db: AsyncSession = Depends(get_db_session),
    workspace_id: int = Depends(get_workspace_id),
):
    stats = await workflow_service.get_workflow_stats(db, workspace_id, workflow_id)
    return stats