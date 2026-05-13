import hashlib
import logging
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.workflow import WorkflowDefinition
from app.models.workflow_trigger import (
    FilterType,
    TriggerExecution,
    TriggerExecutionStatus,
    TriggerMetrics,
    WorkflowTrigger,
)

logger = logging.getLogger(__name__)


async def get_trigger_by_id(
    db: AsyncSession,
    trigger_id: int,
    workspace_id: int,
) -> WorkflowTrigger | None:
    stmt = (
        select(WorkflowTrigger)
        .options(selectinload(WorkflowTrigger.executions))
        .where(
            and_(
                WorkflowTrigger.id == trigger_id,
                WorkflowTrigger.workspace_id == workspace_id,
            )
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_triggers(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int | None = None,
    source: str | None = None,
    status: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[WorkflowTrigger], int]:
    query = select(WorkflowTrigger).where(WorkflowTrigger.workspace_id == workspace_id)

    if workflow_definition_id:
        query = query.where(WorkflowTrigger.workflow_definition_id == workflow_definition_id)
    if source:
        query = query.where(WorkflowTrigger.source == source)
    if status:
        query = query.where(WorkflowTrigger.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(WorkflowTrigger.priority.desc(), WorkflowTrigger.created_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    triggers = list(result.scalars().all())

    return triggers, total


async def create_trigger(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int,
    name: str,
    description: str | None,
    source: str,
    filters: list[dict[str, Any]],
    priority: int,
    created_by: int,
) -> WorkflowTrigger:
    trigger = WorkflowTrigger(
        workspace_id=workspace_id,
        workflow_definition_id=workflow_definition_id,
        name=name,
        description=description,
        source=source,
        filters=filters,
        priority=priority,
        created_by=created_by,
    )
    db.add(trigger)
    await db.commit()
    await db.refresh(trigger)
    return trigger


async def update_trigger(
    db: AsyncSession,
    trigger: WorkflowTrigger,
    name: str | None = None,
    description: str | None = None,
    status: str | None = None,
    filters: list[dict[str, Any]] | None = None,
    priority: int | None = None,
) -> WorkflowTrigger:
    if name is not None:
        trigger.name = name
    if description is not None:
        trigger.description = description
    if status is not None:
        trigger.status = status
    if filters is not None:
        trigger.filters = filters
    if priority is not None:
        trigger.priority = priority

    trigger.updated_at = datetime.utcnow()
    await db.commit()
    await db.refresh(trigger)
    return trigger


async def delete_trigger(db: AsyncSession, trigger: WorkflowTrigger) -> None:
    await db.delete(trigger)
    await db.commit()


async def create_trigger_execution(
    db: AsyncSession,
    workspace_id: int,
    workflow_trigger_id: int,
    event_id: int,
    dedupe_key: str,
    event_payload: dict[str, Any],
) -> TriggerExecution:
    execution = TriggerExecution(
        workspace_id=workspace_id,
        workflow_trigger_id=workflow_trigger_id,
        event_id=event_id,
        dedupe_key=dedupe_key,
        status=TriggerExecutionStatus.pending,
        event_payload=event_payload,
    )
    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def get_trigger_execution(
    db: AsyncSession,
    execution_id: int,
    workspace_id: int,
) -> TriggerExecution | None:
    stmt = select(TriggerExecution).where(
        and_(
            TriggerExecution.id == execution_id,
            TriggerExecution.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_execution_by_dedupe(
    db: AsyncSession,
    dedupe_key: str,
    trigger_id: int,
) -> TriggerExecution | None:
    stmt = select(TriggerExecution).where(
        and_(
            TriggerExecution.dedupe_key == dedupe_key,
            TriggerExecution.workflow_trigger_id == trigger_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def update_trigger_execution(
    db: AsyncSession,
    execution: TriggerExecution,
    status: TriggerExecutionStatus | None = None,
    workflow_execution_id: int | None = None,
    error: str | None = None,
    latency_ms: int | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
) -> TriggerExecution:
    if status:
        execution.status = status
    if workflow_execution_id:
        execution.workflow_execution_id = workflow_execution_id
    if error:
        execution.error = error
    if latency_ms:
        execution.latency_ms = latency_ms
    if started_at:
        execution.started_at = started_at
    if completed_at:
        execution.completed_at = completed_at

    await db.commit()
    await db.refresh(execution)
    return execution


async def list_trigger_executions(
    db: AsyncSession,
    workspace_id: int,
    trigger_id: int | None = None,
    status: TriggerExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[TriggerExecution], int]:
    query = select(TriggerExecution).where(TriggerExecution.workspace_id == workspace_id)

    if trigger_id:
        query = query.where(TriggerExecution.workflow_trigger_id == trigger_id)
    if status:
        query = query.where(TriggerExecution.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(TriggerExecution.created_at.desc()).offset(offset).limit(limit)
    result = await db.execute(query)
    executions = list(result.scalars().all())

    return executions, total


async def get_trigger_stats(
    db: AsyncSession,
    workspace_id: int,
    trigger_id: int | None = None,
) -> dict[str, Any]:
    query = select(TriggerExecution).where(TriggerExecution.workspace_id == workspace_id)

    if trigger_id:
        query = query.where(TriggerExecution.workflow_trigger_id == trigger_id)

    result = await db.execute(query)
    executions = list(result.scalars().all())

    total = len(executions)
    completed = sum(1 for e in executions if e.status == TriggerExecutionStatus.completed)
    failed = sum(1 for e in executions if e.status == TriggerExecutionStatus.failed)
    skipped_duplicate = sum(1 for e in executions if e.status == TriggerExecutionStatus.duplicate)

    latencies = [e.latency_ms for e in executions if e.latency_ms is not None]
    avg_latency = sum(latencies) / len(latencies) if latencies else None

    return {
        "total_executions": total,
        "completed": completed,
        "failed": failed,
        "skipped_duplicate": skipped_duplicate,
        "avg_latency_ms": avg_latency,
    }


async def get_workflow_trigger_stats(
    db: AsyncSession,
    workspace_id: int,
) -> dict[str, Any]:
    query = select(WorkflowTrigger).where(WorkflowTrigger.workspace_id == workspace_id)
    result = await db.execute(query)
    triggers = list(result.scalars().all())

    total_triggers = len(triggers)
    active_triggers = sum(1 for t in triggers if t.status == "active")
    paused_triggers = sum(1 for t in triggers if t.status == "paused")

    exec_query = select(TriggerExecution).where(TriggerExecution.workspace_id == workspace_id)
    exec_result = await db.execute(exec_query)
    executions = list(exec_result.scalars().all())

    total_executions = len(executions)
    completed = sum(1 for e in executions if e.status == TriggerExecutionStatus.completed)
    failed = sum(1 for e in executions if e.status == TriggerExecutionStatus.failed)
    duplicate = sum(1 for e in executions if e.status == TriggerExecutionStatus.duplicate)

    return {
        "total_triggers": total_triggers,
        "active_triggers": active_triggers,
        "paused_triggers": paused_triggers,
        "total_executions": total_executions,
        "completed_executions": completed,
        "failed_executions": failed,
        "duplicate_skipped": duplicate,
    }


async def record_trigger_metrics(
    db: AsyncSession,
    workspace_id: int,
    trigger_id: int,
    event_type: str,
    triggered: bool = True,
    matched: bool = False,
    executed: bool = False,
    failed: bool = False,
    duplicate: bool = False,
    latency_ms: int | None = None,
) -> None:
    period_start = datetime.utcnow().replace(minute=0, second=0, microsecond=0)
    period_end = period_start + timedelta(hours=1)

    stmt = select(TriggerMetrics).where(
        and_(
            TriggerMetrics.workspace_id == workspace_id,
            TriggerMetrics.trigger_id == trigger_id,
            TriggerMetrics.period_start == period_start,
        )
    )
    result = await db.execute(stmt)
    metrics = result.scalar_one_or_none()

    if metrics:
        if triggered:
            metrics.triggered_count += 1
        if matched:
            metrics.matched_count += 1
        if executed:
            metrics.executed_count += 1
        if failed:
            metrics.failed_count += 1
        if duplicate:
            metrics.skipped_duplicate_count += 1

        if latency_ms:
            if metrics.avg_latency_ms:
                metrics.avg_latency_ms = (metrics.avg_latency_ms + latency_ms) / 2
            else:
                metrics.avg_latency_ms = latency_ms
    else:
        metrics = TriggerMetrics(
            workspace_id=workspace_id,
            trigger_id=trigger_id,
            event_type=event_type,
            triggered_count=1 if triggered else 0,
            matched_count=1 if matched else 0,
            executed_count=1 if executed else 0,
            failed_count=1 if failed else 0,
            skipped_duplicate_count=1 if duplicate else 0,
            avg_latency_ms=latency_ms,
            period_start=period_start,
            period_end=period_end,
        )
        db.add(metrics)

    await db.commit()


def generate_event_dedupe_key(
    event_type: str,
    workspace_id: int,
    event_payload: dict[str, Any],
) -> str:
    payload_str = str(sorted(event_payload.items()))
    payload_hash = hashlib.sha256(payload_str.encode()).hexdigest()[:16]
    return f"event:{event_type}:{workspace_id}:{payload_hash}"