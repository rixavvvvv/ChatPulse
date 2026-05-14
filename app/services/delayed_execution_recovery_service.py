"""
Delayed execution recovery service.

Handles recovery of delayed workflow executions after timeout events,
enabling resumption of delayed nodes while preserving execution state.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import WorkflowExecution, ExecutionStatus
from app.models.workflow_delayed import (
    DelayedExecution,
    DelayedExecutionStatus,
)


class DelayedExecutionRecoveryService:
    """Manages recovery and resumption of delayed executions after timeouts."""

    async def find_resumable_delayed_executions(
        self,
        session: AsyncSession,
        workspace_id: int,
        execution_id: Optional[int] = None,
        limit: int = 100,
    ) -> list[DelayedExecution]:
        """Find delayed executions that can be resumed.

        Delayed executions in PENDING or SCHEDULED status can be resumed
        after the parent execution times out and recovers.

        Args:
            session: Database session.
            workspace_id: Workspace ID to filter.
            execution_id: Optional execution ID to filter.
            limit: Maximum results to return.

        Returns:
            List of resumable delayed executions.
        """
        stmt = select(DelayedExecution).where(
            (DelayedExecution.workspace_id == workspace_id)
            & (
                DelayedExecution.status.in_(
                    (
                        DelayedExecutionStatus.scheduled,
                        DelayedExecutionStatus.pending,
                    )
                )
            ),
        )

        if execution_id:
            stmt = stmt.where(
                DelayedExecution.workflow_execution_id == execution_id,
            )

        stmt = stmt.limit(limit)
        result = await session.execute(stmt)
        return result.scalars().all()

    async def mark_resumable_after_timeout(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
    ) -> int:
        """Mark all delayed executions in an execution as resumable.

        Sets status to PENDING so delayed task processor can resume them.

        Args:
            session: Database session.
            execution: Timed out execution.

        Returns:
            Number of delayed executions marked as resumable.
        """
        stmt = select(DelayedExecution).where(
            (DelayedExecution.workflow_execution_id == execution.id)
            & (
                DelayedExecution.status.in_(
                    (
                        DelayedExecutionStatus.scheduled,
                        DelayedExecutionStatus.pending,
                        DelayedExecutionStatus.running,
                    )
                )
            ),
        )

        result = await session.execute(stmt)
        delayed_execs = result.scalars().all()

        count = 0
        for delayed_exec in delayed_execs:
            # Mark as pending so it can be picked up for execution
            delayed_exec.status = DelayedExecutionStatus.pending
            session.add(delayed_exec)
            count += 1

        await session.flush()
        return count

    async def resume_delayed_execution(
        self,
        session: AsyncSession,
        delayed_execution: DelayedExecution,
        parent_execution: WorkflowExecution,
    ) -> bool:
        """Resume a delayed execution within parent execution context.

        Args:
            session: Database session.
            delayed_execution: Delayed execution to resume.
            parent_execution: Parent workflow execution.

        Returns:
            True if resume was initiated, False otherwise.
        """
        # Check if parent execution allows resumption
        if parent_execution.status == ExecutionStatus.cancelled:
            # Parent is cancelled, don't resume
            delayed_execution.status = DelayedExecutionStatus.cancelled
            session.add(delayed_execution)
            await session.flush()
            return False

        if parent_execution.status in (
            ExecutionStatus.completed,
            ExecutionStatus.failed,
        ):
            # Parent is terminal, can resume if configured to do so
            delayed_execution.status = DelayedExecutionStatus.pending
            session.add(delayed_execution)
            await session.flush()
            return True

        # Parent is running or paused, safe to resume
        delayed_execution.status = DelayedExecutionStatus.pending
        session.add(delayed_execution)
        await session.flush()
        return True

    async def get_delayed_execution_stats(
        self,
        session: AsyncSession,
        workspace_id: int,
        execution_id: Optional[int] = None,
    ) -> dict:
        """Get statistics about delayed executions.

        Args:
            session: Database session.
            workspace_id: Workspace ID to filter.
            execution_id: Optional execution ID to filter.

        Returns:
            Dictionary with delayed execution statistics.
        """
        stmt = select(DelayedExecution).where(
            DelayedExecution.workspace_id == workspace_id,
        )

        if execution_id:
            stmt = stmt.where(
                DelayedExecution.workflow_execution_id == execution_id,
            )

        result = await session.execute(stmt)
        delayed_execs = result.scalars().all()

        stats = {
            "total": len(delayed_execs),
            "scheduled": 0,
            "pending": 0,
            "running": 0,
            "completed": 0,
            "failed": 0,
            "cancelled": 0,
            "expired": 0,
            "resumable": 0,
            "overdue": 0,
        }

        now = datetime.now(timezone.utc)
        for delayed_exec in delayed_execs:
            status = delayed_exec.status
            if status == DelayedExecutionStatus.scheduled:
                stats["scheduled"] += 1
            elif status == DelayedExecutionStatus.pending:
                stats["pending"] += 1
            elif status == DelayedExecutionStatus.running:
                stats["running"] += 1
            elif status == DelayedExecutionStatus.completed:
                stats["completed"] += 1
            elif status == DelayedExecutionStatus.failed:
                stats["failed"] += 1
            elif status == DelayedExecutionStatus.cancelled:
                stats["cancelled"] += 1
            elif status == DelayedExecutionStatus.expired:
                stats["expired"] += 1

            # Count resumable (scheduled or pending)
            if status in (DelayedExecutionStatus.scheduled, DelayedExecutionStatus.pending):
                stats["resumable"] += 1

            # Count overdue (scheduled time passed)
            if delayed_exec.scheduled_at < now and status == DelayedExecutionStatus.scheduled:
                stats["overdue"] += 1

        return stats

    async def extend_delayed_execution_deadline(
        self,
        session: AsyncSession,
        delayed_execution: DelayedExecution,
        extension_seconds: int,
    ) -> None:
        """Extend deadline for a delayed execution.

        Used to give delayed executions more time after recovery from timeout.

        Args:
            session: Database session.
            delayed_execution: Delayed execution to extend.
            extension_seconds: Number of seconds to extend deadline.
        """
        new_scheduled_at = delayed_execution.scheduled_at.replace(
            year=delayed_execution.scheduled_at.year,
            month=delayed_execution.scheduled_at.month,
            day=delayed_execution.scheduled_at.day,
        )

        # Extend scheduled time
        if delayed_execution.scheduled_at:
            from datetime import timedelta
            delayed_execution.scheduled_at = delayed_execution.scheduled_at + \
                timedelta(seconds=extension_seconds)

        # Extend window if present
        if delayed_execution.window_end:
            from datetime import timedelta
            delayed_execution.window_end = delayed_execution.window_end + \
                timedelta(seconds=extension_seconds)

        session.add(delayed_execution)
        await session.flush()

    async def cancel_delayed_execution(
        self,
        session: AsyncSession,
        delayed_execution: DelayedExecution,
        reason: str = "execution_cancelled",
    ) -> None:
        """Cancel a delayed execution.

        Args:
            session: Database session.
            delayed_execution: Delayed execution to cancel.
            reason: Reason for cancellation.
        """
        if delayed_execution.status not in (
            DelayedExecutionStatus.completed,
            DelayedExecutionStatus.failed,
            DelayedExecutionStatus.cancelled,
        ):
            delayed_execution.status = DelayedExecutionStatus.cancelled
            session.add(delayed_execution)
            await session.flush()

    async def cleanup_expired_delayed_executions(
        self,
        session: AsyncSession,
        workspace_id: int,
        days_old: int = 30,
    ) -> int:
        """Clean up old expired delayed executions.

        Args:
            session: Database session.
            workspace_id: Workspace ID.
            days_old: Age threshold in days.

        Returns:
            Number of cleaned up executions.
        """
        from datetime import timedelta
        cutoff_time = datetime.now(timezone.utc) - timedelta(days=days_old)

        stmt = select(DelayedExecution).where(
            (DelayedExecution.workspace_id == workspace_id)
            & (DelayedExecution.status == DelayedExecutionStatus.expired)
            & (DelayedExecution.created_at < cutoff_time),
        )

        result = await session.execute(stmt)
        expired = result.scalars().all()

        count = 0
        for delayed_exec in expired:
            await session.delete(delayed_exec)
            count += 1

        await session.flush()
        return count
