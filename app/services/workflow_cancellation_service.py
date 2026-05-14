"""
Workflow execution cancellation service.

Handles execution and node cancellation, cancellation propagation to child nodes,
resource cleanup, and cancellation event generation.
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    ExecutionStatus,
    NodeExecution,
    WorkflowEdge,
    WorkflowExecution,
)


class WorkflowCancellationService:
    """Manages workflow execution and node cancellation."""

    async def cancel_execution(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
        reason: str = "user_request",
        propagate: bool = True,
    ) -> None:
        """Cancel a workflow execution and optionally propagate to running nodes.

        Args:
            session: Database session.
            execution: Workflow execution to cancel.
            reason: Reason for cancellation (e.g., 'timeout', 'user_request').
            propagate: Whether to propagate cancellation to child nodes.
        """
        now = datetime.now(timezone.utc)

        # Only cancel if not already terminal
        if execution.status not in (
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.cancelled,
        ):
            execution.status = ExecutionStatus.cancelled
            execution.cancelled_at = now
            execution.cancellation_reason = reason

            if propagate:
                # Propagate cancellation to all running node executions
                await self._propagate_cancellation_to_nodes(
                    session,
                    execution,
                    reason=reason,
                )

            session.add(execution)
            await session.flush()

    async def cancel_node_execution(
        self,
        session: AsyncSession,
        node_execution: NodeExecution,
        reason: str = "execution_cancelled",
        propagate: bool = True,
    ) -> None:
        """Cancel a node execution and optionally propagate to children.

        Args:
            session: Database session.
            node_execution: Node execution to cancel.
            reason: Reason for cancellation.
            propagate: Whether to propagate to downstream nodes.
        """
        now = datetime.now(timezone.utc)

        # Only cancel if not already terminal
        if node_execution.status not in (
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.cancelled,
        ):
            node_execution.status = ExecutionStatus.cancelled
            node_execution.completed_at = now
            session.add(node_execution)

            if propagate:
                # Propagate to downstream nodes
                await self._propagate_cancellation_downstream(
                    session,
                    node_execution.workflow_execution_id,
                    node_execution.node_id,
                    reason=reason,
                )

            await session.flush()

    async def _propagate_cancellation_to_nodes(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
        reason: str,
    ) -> None:
        """Propagate execution cancellation to all running nodes.

        Args:
            session: Database session.
            execution: Execution being cancelled.
            reason: Reason for cancellation.
        """
        # Get all running node executions for this workflow
        stmt = select(NodeExecution).where(
            (NodeExecution.workflow_execution_id == execution.id)
            & (
                NodeExecution.status.in_(
                    (ExecutionStatus.pending, ExecutionStatus.running)
                )
            ),
        )
        result = await session.execute(stmt)
        node_executions = result.scalars().all()

        for node_exec in node_executions:
            await self.cancel_node_execution(
                session,
                node_exec,
                reason=reason,
                propagate=True,
            )

    async def _propagate_cancellation_downstream(
        self,
        session: AsyncSession,
        execution_id: int,
        from_node_id: str,
        reason: str,
    ) -> None:
        """Propagate cancellation to downstream nodes in workflow.

        Finds edges starting from the given node and cancels those target nodes.

        Args:
            session: Database session.
            execution_id: Workflow execution ID.
            from_node_id: Node ID to propagate from.
            reason: Reason for cancellation.
        """
        # Get the workflow execution
        execution = await session.get(WorkflowExecution, execution_id)
        if not execution:
            return

        # Get workflow definition
        definition = execution.definition
        if not definition:
            return

        # Find all edges starting from this node
        stmt = select(WorkflowEdge).where(
            (WorkflowEdge.workflow_definition_id == definition.id)
            & (WorkflowEdge.source_node_id == from_node_id),
        )
        result = await session.execute(stmt)
        edges = result.scalars().all()

        # Cancel target nodes
        for edge in edges:
            stmt = select(NodeExecution).where(
                (NodeExecution.workflow_execution_id == execution_id)
                & (NodeExecution.node_id == edge.target_node_id)
                & (
                    NodeExecution.status.in_(
                        (ExecutionStatus.pending, ExecutionStatus.running)
                    )
                ),
            )
            result = await session.execute(stmt)
            target_nodes = result.scalars().all()

            for target_node in target_nodes:
                await self.cancel_node_execution(
                    session,
                    target_node,
                    reason=f"{reason} (parent cancelled)",
                    propagate=True,
                )

    async def get_cancellable_executions(
        self,
        session: AsyncSession,
        workspace_id: int,
        limit: int = 100,
    ) -> list[WorkflowExecution]:
        """Get all cancellable executions (running/pending) in workspace.

        Args:
            session: Database session.
            workspace_id: Workspace ID to filter.
            limit: Maximum results to return.

        Returns:
            List of cancellable executions.
        """
        stmt = (
            select(WorkflowExecution)
            .where(
                (WorkflowExecution.workspace_id == workspace_id)
                & (
                    WorkflowExecution.status.in_(
                        (ExecutionStatus.pending, ExecutionStatus.running)
                    )
                ),
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    async def get_cancellable_nodes(
        self,
        session: AsyncSession,
        execution_id: int,
        limit: int = 100,
    ) -> list[NodeExecution]:
        """Get all cancellable nodes (running/pending) in execution.

        Args:
            session: Database session.
            execution_id: Execution ID to filter.
            limit: Maximum results to return.

        Returns:
            List of cancellable node executions.
        """
        stmt = (
            select(NodeExecution)
            .where(
                (NodeExecution.workflow_execution_id == execution_id)
                & (
                    NodeExecution.status.in_(
                        (ExecutionStatus.pending, ExecutionStatus.running)
                    )
                ),
            )
            .limit(limit)
        )
        result = await session.execute(stmt)
        return result.scalars().all()

    def is_cancellation_in_progress(
        self,
        execution: WorkflowExecution,
        grace_period_seconds: int,
    ) -> bool:
        """Check if execution is in cancellation grace period.

        Grace period allows in-flight cleanup operations to complete.

        Args:
            execution: Execution to check.
            grace_period_seconds: Grace period duration in seconds.

        Returns:
            True if execution is being cancelled but within grace period.
        """
        if execution.cancelled_at is None:
            return False

        now = datetime.now(timezone.utc)
        elapsed = (now - execution.cancelled_at).total_seconds()
        return elapsed < grace_period_seconds

    def should_force_cancel(
        self,
        execution: WorkflowExecution,
        grace_period_seconds: int,
    ) -> bool:
        """Check if force cancellation is needed (grace period exceeded).

        Args:
            execution: Execution to check.
            grace_period_seconds: Grace period duration in seconds.

        Returns:
            True if cancellation was requested and grace period exceeded.
        """
        if execution.cancelled_at is None:
            return False

        if execution.status == ExecutionStatus.cancelled:
            return False

        now = datetime.now(timezone.utc)
        elapsed = (now - execution.cancelled_at).total_seconds()
        return elapsed >= grace_period_seconds

    async def force_cancel_execution(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
    ) -> None:
        """Force cancel execution by terminating all child nodes immediately.

        Used when grace period expires and graceful cancellation didn't complete.

        Args:
            session: Database session.
            execution: Execution to force cancel.
        """
        now = datetime.now(timezone.utc)

        # Get all non-terminal nodes
        stmt = select(NodeExecution).where(
            (NodeExecution.workflow_execution_id == execution.id)
            & (
                ~NodeExecution.status.in_(
                    (
                        ExecutionStatus.completed,
                        ExecutionStatus.failed,
                        ExecutionStatus.cancelled,
                    )
                )
            ),
        )
        result = await session.execute(stmt)
        nodes = result.scalars().all()

        for node in nodes:
            node.status = ExecutionStatus.cancelled
            node.completed_at = now
            session.add(node)

        # Mark execution as cancelled
        execution.status = ExecutionStatus.cancelled
        execution.completed_at = now
        if execution.cancelled_at is None:
            execution.cancelled_at = now
            execution.cancellation_reason = "force_cancel"

        session.add(execution)
        await session.flush()
