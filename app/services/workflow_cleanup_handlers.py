"""
Workflow execution cleanup handlers.

Manages resource cleanup when executions are cancelled or timed out,
including celery task cancellation, delayed execution state restoration,
and execution context cleanup.
"""

from datetime import datetime, timezone
from typing import Any, Callable, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    DelayedExecution,
    DelayedExecutionStatus,
    NodeExecution,
    WorkflowExecution,
)


# Type for cleanup handler functions
CleanupHandler = Callable[[AsyncSession, Any], Any]


class ExecutionCleanupHandler:
    """Base handler for execution cleanup operations."""

    async def execute(self, session: AsyncSession, *args, **kwargs) -> None:
        """Execute cleanup operation.

        Args:
            session: Database session.
            *args: Positional arguments.
            **kwargs: Keyword arguments.
        """
        raise NotImplementedError


class CeleryTaskCleanupHandler(ExecutionCleanupHandler):
    """Cancels Celery tasks associated with execution."""

    def __init__(self, celery_app):
        """Initialize with Celery app.

        Args:
            celery_app: Celery application instance.
        """
        self.celery_app = celery_app

    async def execute(
        self,
        session: AsyncSession,
        execution_id: str,
        task_ids: Optional[list[str]] = None,
    ) -> None:
        """Cancel Celery tasks.

        Args:
            session: Database session.
            execution_id: Workflow execution ID.
            task_ids: Specific task IDs to cancel. If None, attempts to cancel all.
        """
        if task_ids:
            for task_id in task_ids:
                try:
                    self.celery_app.control.revoke(
                        task_id,
                        terminate=True,
                        signal="SIGTERM",
                    )
                except Exception as e:
                    # Log but don't fail - task may already be complete
                    pass


class DelayedExecutionCleanupHandler(ExecutionCleanupHandler):
    """Restores delayed executions to pending state for resumption after timeout."""

    async def execute(
        self,
        session: AsyncSession,
        execution_id: int,
        make_resumable: bool = True,
    ) -> None:
        """Restore delayed executions for resumption.

        When a workflow execution times out but has delayed nodes,
        mark them as pending so they can be resumed after recovery.

        Args:
            session: Database session.
            execution_id: Workflow execution ID.
            make_resumable: Whether to restore to pending (resumable) status.
        """
        from sqlalchemy import select

        # Find all delayed executions for this workflow execution
        stmt = select(DelayedExecution).where(
            DelayedExecution.workflow_execution_id == execution_id,
        )
        result = await session.execute(stmt)
        delayed_execs = result.scalars().all()

        now = datetime.now(timezone.utc)

        for delayed_exec in delayed_execs:
            if delayed_exec.status not in (
                DelayedExecutionStatus.completed,
                DelayedExecutionStatus.failed,
                DelayedExecutionStatus.expired,
            ):
                if make_resumable:
                    # Mark as pending so it can be resumed
                    delayed_exec.status = DelayedExecutionStatus.pending
                else:
                    # Mark as cancelled/expired
                    delayed_exec.status = DelayedExecutionStatus.expired

                session.add(delayed_exec)

        await session.flush()


class ExecutionContextCleanupHandler(ExecutionCleanupHandler):
    """Cleans up execution context and state."""

    async def execute(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
        clear_context: bool = False,
        clear_results: bool = False,
    ) -> None:
        """Clean up execution context.

        Args:
            session: Database session.
            execution: Workflow execution to clean up.
            clear_context: Whether to clear execution context data.
            clear_results: Whether to clear node execution results.
        """
        if clear_context and execution.context:
            # Preserve only essential context, clear temporary data
            execution.context = {
                k: v
                for k, v in execution.context.items()
                if k in ("preserved_keys", "essential_state")
            }

        if clear_results:
            # Clear node output data to free memory
            for node_exec in execution.node_executions:
                if node_exec.output_data:
                    node_exec.output_data = {}
                    session.add(node_exec)

        session.add(execution)
        await session.flush()


class NodeExecutionCleanupHandler(ExecutionCleanupHandler):
    """Cleans up individual node execution state."""

    async def execute(
        self,
        session: AsyncSession,
        node_execution: NodeExecution,
        clear_data: bool = False,
    ) -> None:
        """Clean up node execution.

        Args:
            session: Database session.
            node_execution: Node execution to clean up.
            clear_data: Whether to clear input/output data.
        """
        if clear_data:
            node_execution.input_data = {}
            node_execution.output_data = {}

        session.add(node_execution)
        await session.flush()


class WorkflowExecutionCleanupRegistry:
    """Registry of cleanup handlers for execution cleanup operations."""

    def __init__(self):
        """Initialize cleanup handler registry."""
        self.handlers: dict[str, ExecutionCleanupHandler] = {}
        self._cleanup_order = [
            "celery_tasks",
            "delayed_execution",
            "execution_context",
        ]

    def register(self, name: str, handler: ExecutionCleanupHandler) -> None:
        """Register a cleanup handler.

        Args:
            name: Handler name (e.g., 'celery_tasks').
            handler: Handler instance.
        """
        self.handlers[name] = handler

    def unregister(self, name: str) -> None:
        """Unregister a cleanup handler.

        Args:
            name: Handler name to remove.
        """
        if name in self.handlers:
            del self.handlers[name]

    async def cleanup_execution(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
        handlers: Optional[list[str]] = None,
        **cleanup_options,
    ) -> dict[str, Optional[Exception]]:
        """Run cleanup handlers for execution.

        Args:
            session: Database session.
            execution: Workflow execution to clean up.
            handlers: Specific handlers to run. If None, runs all in order.
            **cleanup_options: Handler-specific options passed to execute().

        Returns:
            Dict mapping handler name to exception (if any).
        """
        results = {}

        # Use specified handlers or default order
        handlers_to_run = handlers or self._cleanup_order

        for handler_name in handlers_to_run:
            if handler_name not in self.handlers:
                continue

            try:
                handler = self.handlers[handler_name]
                await handler.execute(session, execution, **cleanup_options)
                results[handler_name] = None
            except Exception as e:
                results[handler_name] = e

        return results

    async def cleanup_node(
        self,
        session: AsyncSession,
        node_execution: NodeExecution,
        handlers: Optional[list[str]] = None,
        **cleanup_options,
    ) -> dict[str, Optional[Exception]]:
        """Run cleanup handlers for node execution.

        Args:
            session: Database session.
            node_execution: Node execution to clean up.
            handlers: Specific handlers to run.
            **cleanup_options: Handler-specific options.

        Returns:
            Dict mapping handler name to exception (if any).
        """
        results = {}

        for handler_name in handlers or ["celery_tasks"]:
            if handler_name not in self.handlers:
                continue

            try:
                handler = self.handlers[handler_name]
                await handler.execute(session, node_execution, **cleanup_options)
                results[handler_name] = None
            except Exception as e:
                results[handler_name] = e

        return results


# Global cleanup registry instance
_cleanup_registry: Optional[WorkflowExecutionCleanupRegistry] = None


def get_cleanup_registry() -> WorkflowExecutionCleanupRegistry:
    """Get or create global cleanup registry.

    Returns:
        Global cleanup registry instance.
    """
    global _cleanup_registry
    if _cleanup_registry is None:
        _cleanup_registry = WorkflowExecutionCleanupRegistry()
    return _cleanup_registry


def initialize_cleanup_registry(celery_app) -> WorkflowExecutionCleanupRegistry:
    """Initialize cleanup registry with default handlers.

    Args:
        celery_app: Celery application instance.

    Returns:
        Initialized cleanup registry.
    """
    global _cleanup_registry
    registry = get_cleanup_registry()

    # Register default handlers
    registry.register("celery_tasks", CeleryTaskCleanupHandler(celery_app))
    registry.register("delayed_execution", DelayedExecutionCleanupHandler())
    registry.register("execution_context", ExecutionContextCleanupHandler())

    return registry
