"""
Celery tasks for event trigger execution.

This module provides:
1. Trigger matching and execution
2. Idempotency guarantees
3. Duplicate prevention
4. Metrics collection
"""

import logging
import time
from datetime import datetime

from redis.asyncio import Redis

from app.core.config import get_settings
from app.models.workflow_trigger import TriggerExecutionStatus
from app.queue.base_tasks import IdempotencyMixin, LongRunningTask
from app.services import workflow_engine, trigger_matching_engine, trigger_service
from app.services.domain_event_service import get_event_by_id

settings = get_settings()
logger = logging.getLogger(__name__)


def trigger_task_routes():
    return {
        "trigger.execute_workflow": {"queue": "trigger_execution"},
        "trigger.process_event": {"queue": "trigger_ingest"},
    }


class ProcessEventTask(LongRunningTask):
    """
    Task that processes incoming domain events and finds matching triggers.
    """

    name = "trigger.process_event"
    max_retries = 3
    default_retry_delay = 5

    def _do_execute(self, event_id: int, event_type: str, workspace_id: int) -> dict:
        import asyncio
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                event = await get_event_by_id(db, event_id)
                if not event:
                    return {"status": "event_not_found"}

                matching_triggers = await trigger_matching_engine.TriggerMatchingEngine(
                    db
                ).find_matching_triggers(
                    event_type=event_type,
                    workspace_id=workspace_id,
                    event_payload=event.payload,
                    correlation_id=event.correlation_id,
                )

                executed_count = 0
                for trigger in matching_triggers:
                    dedupe_key = trigger_matching_engine.generate_dedupe_key(
                        event_type=event_type,
                        workspace_id=workspace_id,
                        event_payload=event.payload,
                        trigger_id=trigger.id,
                    )

                    from celery import chain
                    result = chain(
                        execute_workflow.s(
                            trigger_id=trigger.id,
                            event_id=event_id,
                            dedupe_key=dedupe_key,
                        )
                    ).apply_async()

                    executed_count += 1

                    await trigger_service.record_trigger_metrics(
                        db,
                        workspace_id=workspace_id,
                        trigger_id=trigger.id,
                        event_type=event_type,
                        triggered=True,
                        matched=True,
                    )

                await db.commit()
                return {
                    "status": "processed",
                    "event_id": event_id,
                    "matching_triggers": len(matching_triggers),
                    "executed": executed_count,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("ProcessEventTask failed event_id=%s error=%s", args[0], exc)


class ExecuteWorkflowTask(LongRunningTask):
    """
    Task that executes a workflow in response to a trigger event.
    Provides idempotency guarantees and duplicate prevention.
    """

    name = "trigger.execute_workflow"
    max_retries = 3
    default_retry_delay = 10

    def _do_execute(
        self,
        trigger_id: int,
        event_id: int,
        dedupe_key: str,
    ) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                start_time = time.time()

                trigger = await trigger_service.get_trigger_by_id(db, trigger_id, 0)
                if not trigger or trigger.status != "active":
                    return {"status": "trigger_inactive"}

                existing = await trigger_service.get_execution_by_dedupe(db, dedupe_key, trigger_id)
                if existing:
                    if existing.status == TriggerExecutionStatus.completed:
                        return {"status": "duplicate", "execution_id": existing.id}
                    elif existing.status == TriggerExecutionStatus.running:
                        return {"status": "already_running", "execution_id": existing.id}

                redis = Redis.from_url(settings.redis_url, decode_responses=True)
                lock_key = f"trigger:lock:{dedupe_key}"
                try:
                    lock_acquired = await redis.set(lock_key, "1", nx=True, ex=300)
                    if not lock_acquired:
                        return {"status": "lock_not_acquired"}
                finally:
                    await redis.aclose()

                event = await get_event_by_id(db, event_id)
                event_payload = event.payload if event else {}

                execution = await trigger_service.create_trigger_execution(
                    db,
                    workspace_id=trigger.workspace_id,
                    workflow_trigger_id=trigger_id,
                    event_id=event_id,
                    dedupe_key=dedupe_key,
                    event_payload=event_payload,
                )

                await trigger_service.update_trigger_execution(
                    db,
                    execution,
                    status=TriggerExecutionStatus.running,
                    started_at=datetime.utcnow(),
                )

                workflow = await trigger_service.get_trigger_by_id(db, trigger_id, trigger.workspace_id)
                workflow_def = await db.get(workflow.workflow_definition_id)

                from sqlalchemy.orm import selectinload
                from app.models.workflow import WorkflowDefinition
                stmt = select(WorkflowDefinition).where(WorkflowDefinition.id == workflow.workflow_definition_id)
                result = await db.execute(stmt)
                workflow_def = result.scalar_one_or_none()

                if not workflow_def:
                    await trigger_service.update_trigger_execution(
                        db,
                        execution,
                        status=TriggerExecutionStatus.failed,
                        error="Workflow definition not found",
                        completed_at=datetime.utcnow(),
                    )
                    return {"status": "workflow_not_found"}

                from sqlalchemy import select
                from app.models.workflow import WorkflowNode, WorkflowEdge
                nodes_result = await db.execute(select(WorkflowNode).where(WorkflowNode.workflow_definition_id == workflow_def.id))
                edges_result = await db.execute(select(WorkflowEdge).where(WorkflowEdge.workflow_definition_id == workflow_def.id))
                workflow_def.nodes = list(nodes_result.scalars().all())
                workflow_def.edges = list(edges_result.scalars().all())

                try:
                    workflow_execution = await workflow_engine.start_workflow(
                        db,
                        workflow_def,
                        event_payload,
                    )

                    latency_ms = int((time.time() - start_time) * 1000)

                    await trigger_service.update_trigger_execution(
                        db,
                        execution,
                        status=TriggerExecutionStatus.completed,
                        workflow_execution_id=workflow_execution.id,
                        completed_at=datetime.utcnow(),
                        latency_ms=latency_ms,
                    )

                    await trigger_service.record_trigger_metrics(
                        db,
                        workspace_id=trigger.workspace_id,
                        trigger_id=trigger_id,
                        event_type=trigger.source.value,
                        executed=True,
                        latency_ms=latency_ms,
                    )

                    return {
                        "status": "completed",
                        "execution_id": execution.id,
                        "workflow_execution_id": workflow_execution.execution_id,
                        "latency_ms": latency_ms,
                    }

                except Exception as e:
                    logger.exception("Workflow execution failed trigger_id=%s", trigger_id)
                    latency_ms = int((time.time() - start_time) * 1000)

                    await trigger_service.update_trigger_execution(
                        db,
                        execution,
                        status=TriggerExecutionStatus.failed,
                        error=str(e),
                        completed_at=datetime.utcnow(),
                        latency_ms=latency_ms,
                    )

                    await trigger_service.record_trigger_metrics(
                        db,
                        workspace_id=trigger.workspace_id,
                        trigger_id=trigger_id,
                        event_type=trigger.source.value,
                        failed=True,
                        latency_ms=latency_ms,
                    )

                    raise

                finally:
                    redis = Redis.from_url(settings.redis_url, decode_responses=True)
                    await redis.delete(lock_key)
                    await redis.aclose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("ExecuteWorkflowTask failed trigger_id=%s error=%s", args[0], exc)


process_event = ProcessEventTask()
execute_workflow = ExecuteWorkflowTask()