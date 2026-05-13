"""
Celery tasks for delayed workflow execution.

This module provides:
1. Delayed execution processing
2. Lease management
3. Recovery from worker crashes
4. Metrics collection
"""

import logging
import time
from datetime import datetime, timezone

from sqlalchemy import and_, select, update

from app.core.config import get_settings
from app.models.workflow_delayed import (
    DelayedExecution,
    DelayedExecutionStatus,
    LeaseStatus,
)
from app.models.workflow import ExecutionStatus
from app.queue.base_tasks import IdempotencyMixin, LongRunningTask
from app.services import delayed_execution_service, workflow_engine

settings = get_settings()
logger = logging.getLogger(__name__)


def delayed_task_routes():
    return {
        "delayed.process_scheduled": {"queue": "delayed_execution"},
        "delayed.recover_stale": {"queue": "delayed_recovery"},
        "delayed.expire_leases": {"queue": "delayed_maintenance"},
    }


class ProcessScheduledDelayedTask(LongRunningTask):
    """
    Task that processes scheduled delayed executions.
    Finds executions ready to run, acquires leases, and executes workflows.
    """

    name = "delayed.process_scheduled"
    max_retries = 2
    default_retry_delay = 10

    def _do_execute(self, batch_size: int = 50) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        worker_id = self.request.id

        async def _run():
            async with async_session() as db:
                executions = await delayed_execution_service.get_pending_delayed_executions(
                    db, limit=batch_size
                )

                processed = 0
                for execution in executions:
                    try:
                        lease = await delayed_execution_service.acquire_lease(
                            db, execution.id, worker_id
                        )

                        if not lease:
                            continue

                        await delayed_execution_service.update_delayed_execution(
                            db,
                            execution,
                            status=DelayedExecutionStatus.running,
                            started_at=datetime.now(timezone.utc),
                        )

                        execution = await delayed_execution_service.get_delayed_execution_by_id(
                            db, execution.id, execution.workspace_id
                        )

                        if not execution or execution.status != DelayedExecutionStatus.running:
                            await delayed_execution_service.release_lease(db, lease)
                            continue

                        from sqlalchemy.orm import selectinload
                        from app.models.workflow import WorkflowDefinition, WorkflowNode, WorkflowEdge

                        stmt = select(WorkflowDefinition).where(WorkflowDefinition.id == execution.workflow_definition_id)
                        result = await db.execute(stmt)
                        workflow_def = result.scalar_one_or_none()

                        if not workflow_def:
                            await delayed_execution_service.update_delayed_execution(
                                db,
                                execution,
                                status=DelayedExecutionStatus.failed,
                                error="Workflow definition not found",
                                completed_at=datetime.now(timezone.utc),
                            )
                            await delayed_execution_service.release_lease(db, lease)
                            continue

                        nodes_result = await db.execute(
                            select(WorkflowNode).where(WorkflowNode.workflow_definition_id == workflow_def.id)
                        )
                        edges_result = await db.execute(
                            select(WorkflowEdge).where(WorkflowEdge.workflow_definition_id == workflow_def.id)
                        )
                        workflow_def.nodes = list(nodes_result.scalars().all())
                        workflow_def.edges = list(edges_result.scalars().all())

                        workflow_execution = await workflow_engine.start_workflow(
                            db,
                            workflow_def,
                            execution.trigger_data,
                        )

                        await delayed_execution_service.update_delayed_execution(
                            db,
                            execution,
                            status=DelayedExecutionStatus.completed,
                            workflow_execution_id=workflow_execution.id,
                            completed_at=datetime.now(timezone.utc),
                        )

                        await delayed_execution_service.release_lease(db, lease)

                        processed += 1
                        logger.info(
                            "Delayed execution completed execution_id=%s workflow_execution_id=%s",
                            execution.execution_id,
                            workflow_execution.execution_id,
                        )

                    except Exception as exc:
                        logger.exception("Failed to process delayed execution id=%s", execution.id)

                        if execution.retry_count < execution.max_retries:
                            await delayed_execution_service.update_delayed_execution(
                                db,
                                execution,
                                status=DelayedExecutionStatus.scheduled,
                                retry_count=execution.retry_count + 1,
                            )
                        else:
                            await delayed_execution_service.update_delayed_execution(
                                db,
                                execution,
                                status=DelayedExecutionStatus.failed,
                                error=str(exc),
                                completed_at=datetime.now(timezone.utc),
                            )

                        if 'lease' in locals():
                            try:
                                await delayed_execution_service.release_lease(db, lease)
                            except Exception:
                                pass

                await db.commit()

                return {
                    "status": "completed",
                    "checked": len(executions),
                    "processed": processed,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("ProcessScheduledDelayedTask failed error=%s", exc)


class RecoverStaleDelayedTask(LongRunningTask):
    """
    Task that recovers delayed executions from stale states.
    Handles cases where workers crashed leaving executions in running/pending state.
    """

    name = "delayed.recover_stale"
    max_retries = 3
    default_retry_delay = 30

    def _do_execute(self, stale_threshold_minutes: int = 10) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from datetime import timedelta

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                stale_threshold = datetime.now(timezone.utc) - timedelta(minutes=stale_threshold_minutes)

                stmt = select(DelayedExecution).where(
                    and_(
                        DelayedExecution.status.in_([DelayedExecutionStatus.running, DelayedExecutionStatus.pending]),
                        DelayedExecution.updated_at < stale_threshold,
                    )
                )
                result = await db.execute(stmt)
                stale_executions = list(result.scalars().all())

                recovered = 0
                for execution in stale_executions:
                    if execution.retry_count < execution.max_retries:
                        await delayed_execution_service.update_delayed_execution(
                            db,
                            execution,
                            status=DelayedExecutionStatus.scheduled,
                            retry_count=execution.retry_count + 1,
                            error="Recovered from stale state",
                        )
                        recovered += 1
                    else:
                        await delayed_execution_service.update_delayed_execution(
                            db,
                            execution,
                            status=DelayedExecutionStatus.failed,
                            error="Max retries exceeded after recovery",
                            completed_at=datetime.now(timezone.utc),
                        )

                await db.commit()

                return {
                    "status": "completed",
                    "stale_found": len(stale_executions),
                    "recovered": recovered,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("RecoverStaleDelayedTask failed error=%s", exc)


class ExpireLeasesTask(LongRunningTask):
    """
    Task that expires old leases to allow other workers to pick up executions.
    """

    name = "delayed.expire_leases"
    max_retries = 2
    default_retry_delay = 60

    def _do_execute(self) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                expired_count = await delayed_execution_service.expire_old_leases(db)

                return {
                    "status": "completed",
                    "leases_expired": expired_count,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        logger.error("ExpireLeasesTask failed error=%s", exc)


process_scheduled = ProcessScheduledDelayedTask()
recover_stale = RecoverStaleDelayedTask()
expire_leases = ExpireLeasesTask()