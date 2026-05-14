"""
Workflow execution timeout management service.

Handles timeout configuration, deadline computation, timeout detection,
and timeout event propagation for workflow and node executions.
"""

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.workflow import ExecutionStatus, NodeExecution, WorkflowExecution


class WorkflowTimeoutService:
    """Manages workflow execution timeouts and deadlines."""

    def __init__(self, settings: Settings):
        """Initialize with configuration.

        Args:
            settings: Global application settings with timeout defaults.
        """
        self.settings = settings

    def compute_execution_timeout_deadline(
        self,
        execution: WorkflowExecution,
        settings: Settings,
    ) -> datetime:
        """Compute timeout deadline for a workflow execution.

        Uses execution-specific timeout if set, falls back to workflow-level,
        then global default.

        Args:
            execution: Workflow execution record.
            settings: Global settings with defaults.

        Returns:
            Datetime of execution timeout deadline.
        """
        timeout_seconds = execution.timeout_seconds
        if timeout_seconds is None:
            # Fall back to workflow-level timeout
            if execution.definition and execution.definition.timeout_seconds:
                timeout_seconds = execution.definition.timeout_seconds
            else:
                # Use global default
                timeout_seconds = settings.workflow_execution_timeout_seconds

        if execution.started_at is None:
            # Use creation time if not yet started
            start_time = execution.created_at
        else:
            start_time = execution.started_at

        return start_time + timedelta(seconds=timeout_seconds)

    def compute_node_timeout_deadline(
        self,
        node_execution: NodeExecution,
        settings: Settings,
    ) -> datetime:
        """Compute timeout deadline for a node execution.

        Uses node-specific timeout if set, falls back to global default.

        Args:
            node_execution: Node execution record.
            settings: Global settings with defaults.

        Returns:
            Datetime of node timeout deadline.
        """
        timeout_seconds = node_execution.timeout_seconds
        if timeout_seconds is None:
            timeout_seconds = settings.workflow_node_timeout_seconds

        if node_execution.started_at is None:
            # Use creation time if not yet started
            start_time = node_execution.created_at
        else:
            start_time = node_execution.started_at

        return start_time + timedelta(seconds=timeout_seconds)

    def is_execution_timed_out(
        self,
        execution: WorkflowExecution,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """Check if workflow execution has exceeded its timeout.

        Args:
            execution: Workflow execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            True if execution is timed out.
        """
        if execution.timeout_at is None:
            return False

        if execution.status in (
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.cancelled,
        ):
            return False

        now = current_time or datetime.now(timezone.utc)
        return now >= execution.timeout_at

    def is_node_timed_out(
        self,
        node_execution: NodeExecution,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """Check if node execution has exceeded its timeout.

        Args:
            node_execution: Node execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            True if node is timed out.
        """
        if node_execution.timeout_at is None:
            return False

        if node_execution.status in (
            ExecutionStatus.completed,
            ExecutionStatus.failed,
            ExecutionStatus.cancelled,
        ):
            return False

        now = current_time or datetime.now(timezone.utc)
        return now >= node_execution.timeout_at

    def get_execution_time_remaining(
        self,
        execution: WorkflowExecution,
        current_time: Optional[datetime] = None,
    ) -> Optional[timedelta]:
        """Get remaining time before execution times out.

        Args:
            execution: Workflow execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            Timedelta of remaining time, or None if no timeout set.
        """
        if execution.timeout_at is None:
            return None

        now = current_time or datetime.now(timezone.utc)
        remaining = execution.timeout_at - now
        return remaining if remaining.total_seconds() > 0 else timedelta(seconds=0)

    def get_node_time_remaining(
        self,
        node_execution: NodeExecution,
        current_time: Optional[datetime] = None,
    ) -> Optional[timedelta]:
        """Get remaining time before node times out.

        Args:
            node_execution: Node execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            Timedelta of remaining time, or None if no timeout set.
        """
        if node_execution.timeout_at is None:
            return None

        now = current_time or datetime.now(timezone.utc)
        remaining = node_execution.timeout_at - now
        return remaining if remaining.total_seconds() > 0 else timedelta(seconds=0)

    def get_execution_elapsed_time(
        self,
        execution: WorkflowExecution,
        current_time: Optional[datetime] = None,
    ) -> timedelta:
        """Get elapsed execution time.

        Args:
            execution: Workflow execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            Timedelta of elapsed time.
        """
        now = current_time or datetime.now(timezone.utc)
        start_time = execution.started_at or execution.created_at
        return now - start_time

    def get_node_elapsed_time(
        self,
        node_execution: NodeExecution,
        current_time: Optional[datetime] = None,
    ) -> timedelta:
        """Get elapsed node execution time.

        Args:
            node_execution: Node execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            Timedelta of elapsed time.
        """
        now = current_time or datetime.now(timezone.utc)
        start_time = node_execution.started_at or node_execution.created_at
        return now - start_time

    def get_timeout_percentage(
        self,
        execution: WorkflowExecution,
        current_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """Get percentage of timeout consumed.

        Useful for alerting when execution approaches timeout.

        Args:
            execution: Workflow execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            Percentage (0-100) of timeout used, or None if no timeout.
        """
        if execution.timeout_at is None or execution.timeout_seconds is None:
            return None

        now = current_time or datetime.now(timezone.utc)
        start_time = execution.started_at or execution.created_at
        elapsed = (now - start_time).total_seconds()
        timeout = execution.timeout_seconds

        if timeout <= 0:
            return 100.0
        return min((elapsed / timeout) * 100, 100.0)

    def get_node_timeout_percentage(
        self,
        node_execution: NodeExecution,
        current_time: Optional[datetime] = None,
    ) -> Optional[float]:
        """Get percentage of node timeout consumed.

        Args:
            node_execution: Node execution to check.
            current_time: Current time (defaults to now in UTC).

        Returns:
            Percentage (0-100) of timeout used, or None if no timeout.
        """
        if node_execution.timeout_at is None or node_execution.timeout_seconds is None:
            return None

        now = current_time or datetime.now(timezone.utc)
        start_time = node_execution.started_at or node_execution.created_at
        elapsed = (now - start_time).total_seconds()
        timeout = node_execution.timeout_seconds

        if timeout <= 0:
            return 100.0
        return min((elapsed / timeout) * 100, 100.0)

    def is_approaching_timeout(
        self,
        execution: WorkflowExecution,
        warning_percentage: float = 80.0,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """Check if execution is approaching its timeout.

        Args:
            execution: Workflow execution to check.
            warning_percentage: Warn when this % of timeout is consumed (default 80%).
            current_time: Current time (defaults to now in UTC).

        Returns:
            True if execution has consumed >= warning_percentage of timeout.
        """
        percentage = self.get_timeout_percentage(execution, current_time)
        if percentage is None:
            return False
        return percentage >= warning_percentage

    def is_node_approaching_timeout(
        self,
        node_execution: NodeExecution,
        warning_percentage: float = 80.0,
        current_time: Optional[datetime] = None,
    ) -> bool:
        """Check if node is approaching its timeout.

        Args:
            node_execution: Node execution to check.
            warning_percentage: Warn when this % of timeout is consumed (default 80%).
            current_time: Current time (defaults to now in UTC).

        Returns:
            True if node has consumed >= warning_percentage of timeout.
        """
        percentage = self.get_node_timeout_percentage(
            node_execution, current_time)
        if percentage is None:
            return False
        return percentage >= warning_percentage
