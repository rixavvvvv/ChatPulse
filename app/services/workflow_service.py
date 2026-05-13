import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.workflow import (
    ExecutionStatus,
    NodeExecution,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowNode,
    WorkflowStatus,
)


async def get_workflow_by_id(
    db: AsyncSession,
    workflow_id: int,
    workspace_id: int,
) -> WorkflowDefinition | None:
    stmt = (
        select(WorkflowDefinition)
        .options(selectinload(WorkflowDefinition.nodes), selectinload(WorkflowDefinition.edges))
        .where(
            and_(
                WorkflowDefinition.id == workflow_id,
                WorkflowDefinition.workspace_id == workspace_id,
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_workflows(
    db: AsyncSession,
    workspace_id: int,
    status: WorkflowStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WorkflowDefinition], int]:
    query = select(WorkflowDefinition).where(WorkflowDefinition.workspace_id == workspace_id)

    if status:
        query = query.where(WorkflowDefinition.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(WorkflowDefinition.updated_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    workflows = list(result.scalars().all())

    return workflows, total


async def create_workflow(
    db: AsyncSession,
    workspace_id: int,
    name: str,
    description: str | None,
    nodes: list[dict[str, Any]],
    edges: list[dict[str, Any]],
    created_by: int,
) -> WorkflowDefinition:
    workflow = WorkflowDefinition(
        workspace_id=workspace_id,
        name=name,
        description=description,
        status=WorkflowStatus.draft,
        definition={"nodes": nodes, "edges": edges},
        created_by=created_by,
    )
    db.add(workflow)
    await db.flush()

    for node_data in nodes:
        node = WorkflowNode(
            workflow_definition_id=workflow.id,
            node_id=node_data["node_id"],
            node_type=node_data["node_type"],
            name=node_data["name"],
            config=node_data.get("config", {}),
            position_x=node_data.get("position", {}).get("x", 0),
            position_y=node_data.get("position", {}).get("y", 0),
        )
        db.add(node)

    for edge_data in edges:
        edge = WorkflowEdge(
            workflow_definition_id=workflow.id,
            edge_id=edge_data["edge_id"],
            source_node_id=edge_data["source_node_id"],
            target_node_id=edge_data["target_node_id"],
            condition=edge_data.get("condition"),
        )
        db.add(edge)

    await db.commit()
    await db.refresh(workflow)
    return workflow


async def update_workflow(
    db: AsyncSession,
    workflow: WorkflowDefinition,
    name: str | None = None,
    description: str | None = None,
    status: WorkflowStatus | None = None,
    nodes: list[dict[str, Any]] | None = None,
    edges: list[dict[str, Any]] | None = None,
) -> WorkflowDefinition:
    if name is not None:
        workflow.name = name
    if description is not None:
        workflow.description = description
    if status is not None:
        workflow.status = status
        if status == WorkflowStatus.published:
            workflow.version += 1

    if nodes is not None or edges is not None:
        existing_nodes = {n.node_id: n for n in workflow.nodes}
        existing_edges = {e.edge_id: e for e in workflow.edges}

        if nodes is not None:
            workflow.definition["nodes"] = nodes

            for node_data in nodes:
                node_id = node_data["node_id"]
                if node_id in existing_nodes:
                    node = existing_nodes[node_id]
                    node.name = node_data["name"]
                    node.node_type = node_data["node_type"]
                    node.config = node_data.get("config", {})
                    node.position_x = node_data.get("position", {}).get("x", 0)
                    node.position_y = node_data.get("position", {}).get("y", 0)
                else:
                    node = WorkflowNode(
                        workflow_definition_id=workflow.id,
                        node_id=node_id,
                        node_type=node_data["node_type"],
                        name=node_data["name"],
                        config=node_data.get("config", {}),
                        position_x=node_data.get("position", {}).get("x", 0),
                        position_y=node_data.get("position", {}).get("y", 0),
                    )
                    db.add(node)

            for node_id, node in existing_nodes.items():
                if node_id not in {n["node_id"] for n in nodes}:
                    await db.delete(node)

        if edges is not None:
            workflow.definition["edges"] = edges

            for edge_data in edges:
                edge_id = edge_data["edge_id"]
                if edge_id in existing_edges:
                    edge = existing_edges[edge_id]
                    edge.source_node_id = edge_data["source_node_id"]
                    edge.target_node_id = edge_data["target_node_id"]
                    edge.condition = edge_data.get("condition")
                else:
                    edge = WorkflowEdge(
                        workflow_definition_id=workflow.id,
                        edge_id=edge_id,
                        source_node_id=edge_data["source_node_id"],
                        target_node_id=edge_data["target_node_id"],
                        condition=edge_data.get("condition"),
                    )
                    db.add(edge)

            for edge_id, edge in existing_edges.items():
                if edge_id not in {e["edge_id"] for e in edges}:
                    await db.delete(edge)

    workflow.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(workflow)
    return workflow


async def delete_workflow(db: AsyncSession, workflow: WorkflowDefinition) -> None:
    await db.delete(workflow)
    await db.commit()


async def create_execution(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int,
    trigger_data: dict[str, Any],
) -> WorkflowExecution:
    execution = WorkflowExecution(
        workspace_id=workspace_id,
        workflow_definition_id=workflow_definition_id,
        execution_id=str(uuid.uuid4()),
        status=ExecutionStatus.pending,
        trigger_data=trigger_data,
        context={},
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def get_execution(
    db: AsyncSession,
    execution_id: str,
    workspace_id: int,
) -> WorkflowExecution | None:
    stmt = (
        select(WorkflowExecution)
        .options(
            selectinload(WorkflowExecution.node_executions),
            selectinload(WorkflowExecution.definition).selectinload(WorkflowDefinition.nodes),
            selectinload(WorkflowExecution.definition).selectinload(WorkflowDefinition.edges),
        )
        .where(
            and_(
                WorkflowExecution.execution_id == execution_id,
                WorkflowExecution.workspace_id == workspace_id,
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_executions(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int | None = None,
    status: ExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WorkflowExecution], int]:
    query = select(WorkflowExecution).where(WorkflowExecution.workspace_id == workspace_id)

    if workflow_definition_id:
        query = query.where(WorkflowExecution.workflow_definition_id == workflow_definition_id)
    if status:
        query = query.where(WorkflowExecution.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(WorkflowExecution.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    executions = list(result.scalars().all())

    return executions, total


async def create_node_execution(
    db: AsyncSession,
    workflow_execution_id: int,
    node_id: str,
    node_type: str,
    input_data: dict[str, Any],
) -> NodeExecution:
    node_execution = NodeExecution(
        workflow_execution_id=workflow_execution_id,
        node_id=node_id,
        node_type=node_type,
        status=ExecutionStatus.pending,
        input_data=input_data,
        output_data={},
    )
    db.add(node_execution)
    await db.commit()
    await db.refresh(node_execution)
    return node_execution


async def update_node_execution(
    db: AsyncSession,
    node_execution: NodeExecution,
    status: ExecutionStatus | None = None,
    output_data: dict[str, Any] | None = None,
    error: str | None = None,
) -> NodeExecution:
    if status:
        node_execution.status = status
    if output_data:
        node_execution.output_data = output_data
    if error:
        node_execution.error = error

    await db.commit()
    await db.refresh(node_execution)
    return node_execution


async def update_execution(
    db: AsyncSession,
    execution: WorkflowExecution,
    status: ExecutionStatus | None = None,
    current_node_id: str | None = None,
    context: dict[str, Any] | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> WorkflowExecution:
    if status:
        execution.status = status
    if current_node_id is not None:
        execution.current_node_id = current_node_id
    if context:
        execution.context.update(context)
    if error:
        execution.error = error
    if started_at:
        execution.started_at = started_at
    if completed_at:
        execution.completed_at = completed_at

    await db.commit()
    await db.refresh(execution)
    return execution


async def get_workflow_stats(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int | None = None,
) -> dict[str, Any]:
    query = select(WorkflowExecution).where(WorkflowExecution.workspace_id == workspace_id)

    if workflow_definition_id:
        query = query.where(WorkflowExecution.workflow_definition_id == workflow_definition_id)

    result = await db.execute(query)
    executions = list(result.scalars().all())

    total = len(executions)
    completed = sum(1 for e in executions if e.status == ExecutionStatus.completed)
    failed = sum(1 for e in executions if e.status == ExecutionStatus.failed)
    running = sum(1 for e in executions if e.status == ExecutionStatus.running)
    pending = sum(1 for e in executions if e.status == ExecutionStatus.pending)

    completed_durations = [
        (e.completed_at - e.started_at).total_seconds() * 1000
        for e in executions
        if e.started_at and e.completed_at and e.status == ExecutionStatus.completed
    ]
    avg_duration = sum(completed_durations) / len(completed_durations) if completed_durations else None

    return {
        "total_executions": total,
        "completed": completed,
        "failed": failed,
        "running": running,
        "pending": pending,
        "average_duration_ms": avg_duration,
    }