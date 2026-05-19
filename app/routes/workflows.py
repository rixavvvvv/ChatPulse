import logging

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
from app.services.workflow_graph_validator import WorkflowGraphValidator
from app.services.workflow_engine import start_workflow

router = APIRouter(prefix="/workflows", tags=["workflows"])
logger = logging.getLogger(__name__)


def _validate_workflow_graph(
    *,
    workspace_id: int,
    name: str,
    created_by: int,
    nodes: list[dict],
    edges: list[dict],
) -> None:
    """Run graph validation before persisting workflow changes."""
    from app.models.workflow import (
        WorkflowDefinition,
        WorkflowEdge,
        WorkflowNode,
        WorkflowStatus as ModelWorkflowStatus,
    )

    workflow = WorkflowDefinition(
        workspace_id=workspace_id,
        name=name,
        description=None,
        status=ModelWorkflowStatus.draft,
        definition={"nodes": nodes, "edges": edges},
        created_by=created_by,
    )
    workflow.nodes = [
        WorkflowNode(
            workflow_definition_id=0,
            node_id=node["node_id"],
            node_type=node["node_type"],
            name=node["name"],
            config=node.get("config", {}),
            position_x=node.get("position", {}).get("x", 0),
            position_y=node.get("position", {}).get("y", 0),
        )
        for node in nodes
    ]
    workflow.edges = [
        WorkflowEdge(
            workflow_definition_id=0,
            edge_id=edge["edge_id"],
            source_node_id=edge["source_node_id"],
            target_node_id=edge["target_node_id"],
            condition=edge.get("condition"),
        )
        for edge in edges
    ]

    validator = WorkflowGraphValidator()
    result = validator.validate_workflow(workflow)
    if not result.is_valid:
        logger.warning(
            "workflow.graph_validation_failed",
            extra={
                "workspace_id": workspace_id,
                "node_count": len(nodes),
                "edge_count": len(edges),
                "errors": [e.to_dict() for e in result.errors],
            },
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Workflow graph validation failed",
                "errors": [e.to_dict() for e in result.errors],
                "warnings": result.warnings,
            },
        )


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

    _validate_workflow_graph(
        workspace_id=workspace_id,
        name=workflow_data.name,
        created_by=current_user.id,
        nodes=nodes,
        edges=edges,
    )
    try:
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
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "workflow.create_failed",
            extra={"workspace_id": workspace_id, "name": workflow_data.name},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to create workflow due to invalid workflow structure or payload.",
        )


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

    if nodes is not None or edges is not None:
        effective_nodes = nodes if nodes is not None else workflow.definition.get("nodes", [])
        effective_edges = edges if edges is not None else workflow.definition.get("edges", [])
        _validate_workflow_graph(
            workspace_id=workspace_id,
            name=workflow_data.name or workflow.name,
            created_by=workflow.created_by,
            nodes=effective_nodes,
            edges=effective_edges,
        )

    if workflow_data.status == WorkflowStatus.published:
        effective_nodes = nodes if nodes is not None else workflow.definition.get("nodes", [])
        effective_edges = edges if edges is not None else workflow.definition.get("edges", [])
        _validate_workflow_graph(
            workspace_id=workspace_id,
            name=workflow_data.name or workflow.name,
            created_by=workflow.created_by,
            nodes=effective_nodes,
            edges=effective_edges,
        )

    try:
        await workflow_service.update_workflow(
            db,
            workflow,
            name=workflow_data.name,
            description=workflow_data.description,
            status=workflow_data.status,
            nodes=nodes,
            edges=edges,
        )
        return await workflow_service.get_workflow_by_id(db, workflow_id, workspace_id)
    except HTTPException:
        raise
    except Exception:
        logger.exception(
            "workflow.update_failed",
            extra={"workspace_id": workspace_id, "workflow_id": workflow_id},
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Unable to update workflow due to invalid workflow structure or payload.",
        )


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
