"""
Workflow timeout metrics and event tracking.

Tracks timeout metrics, emits timeout events, and records timeout history
for monitoring and observability.
"""

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.workflow import (
    ExecutionStatus,
    NodeExecution,
    WorkflowExecution,
)


class TimeoutEventType(str, Enum):
    """Types of timeout-related events."""

    execution_timeout = "execution_timeout"
    execution_timeout_warning = "execution_timeout_warning"
    node_timeout = "node_timeout"
    node_timeout_warning = "node_timeout_warning"
    cancellation_initiated = "cancellation_initiated"
    cancellation_completed = "cancellation_completed"
    cancellation_grace_period_exceeded = "cancellation_grace_period_exceeded"


@dataclass
class TimeoutEvent:
    """Event data for timeout-related occurrences."""

    event_type: TimeoutEventType
    workspace_id: int
    execution_id: int
    node_id: Optional[str] = None
    reason: Optional[str] = None
    timeout_seconds: Optional[int] = None
    elapsed_seconds: Optional[float] = None
    remaining_seconds: Optional[float] = None
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Convert event to dictionary representation."""
        data = asdict(self)
        data["event_type"] = self.event_type.value
        data["timestamp"] = self.timestamp.isoformat()
        return data


@dataclass
class TimeoutMetrics:
    """Aggregated timeout metrics."""

    workspace_id: int
    total_executions: int = 0
    total_timeouts: int = 0
    total_cancellations: int = 0
    avg_timeout_percentage: float = 0.0
    max_timeout_percentage: float = 0.0
    node_timeouts: int = 0
    grace_period_exceeded_count: int = 0
    recovered_from_timeout: int = 0
    timestamp: datetime = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now(timezone.utc)

    def to_dict(self) -> dict:
        """Convert metrics to dictionary representation."""
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


class WorkflowTimeoutEventBus:
    """Event bus for timeout-related events."""

    def __init__(self):
        """Initialize event bus."""
        self._listeners: dict[TimeoutEventType, list] = {}
        self._event_history: list[TimeoutEvent] = []

    def subscribe(
        self,
        event_type: TimeoutEventType,
        callback,
    ) -> None:
        """Subscribe to timeout events.

        Args:
            event_type: Type of event to subscribe to.
            callback: Async callback function to invoke on event.
        """
        if event_type not in self._listeners:
            self._listeners[event_type] = []
        self._listeners[event_type].append(callback)

    def unsubscribe(
        self,
        event_type: TimeoutEventType,
        callback,
    ) -> None:
        """Unsubscribe from timeout events.

        Args:
            event_type: Type of event.
            callback: Callback to remove.
        """
        if event_type in self._listeners:
            self._listeners[event_type] = [
                cb for cb in self._listeners[event_type] if cb != callback
            ]

    async def emit(self, event: TimeoutEvent) -> None:
        """Emit timeout event to all subscribers.

        Args:
            event: Timeout event to emit.
        """
        # Record in history
        self._event_history.append(event)

        # Call listeners
        if event.event_type in self._listeners:
            for callback in self._listeners[event.event_type]:
                try:
                    await callback(event)
                except Exception as e:
                    # Log but don't fail
                    pass

    def get_event_history(
        self,
        workspace_id: int,
        event_type: Optional[TimeoutEventType] = None,
        limit: int = 100,
    ) -> list[TimeoutEvent]:
        """Get event history for workspace.

        Args:
            workspace_id: Workspace ID to filter.
            event_type: Optional event type filter.
            limit: Maximum results to return.

        Returns:
            List of timeout events.
        """
        events = [
            e
            for e in self._event_history
            if e.workspace_id == workspace_id
            and (event_type is None or e.event_type == event_type)
        ]
        return events[-limit:]


class WorkflowTimeoutMetricsCollector:
    """Collects and aggregates timeout metrics."""

    def __init__(self, event_bus: Optional[WorkflowTimeoutEventBus] = None):
        """Initialize metrics collector.

        Args:
            event_bus: Optional event bus for event tracking.
        """
        self.event_bus = event_bus or WorkflowTimeoutEventBus()
        self._metrics: dict[int, TimeoutMetrics] = {}

    async def record_execution_timeout(
        self,
        session: AsyncSession,
        execution: WorkflowExecution,
        timeout_percentage: float,
    ) -> None:
        """Record execution timeout event and metrics.

        Args:
            session: Database session.
            execution: Timed out execution.
            timeout_percentage: Percentage of timeout used.
        """
        event = TimeoutEvent(
            event_type=TimeoutEventType.execution_timeout,
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
            reason="execution_exceeded_timeout",
            timeout_seconds=execution.timeout_seconds,
            elapsed_seconds=(execution.completed_at or datetime.now(
                timezone.utc) - (execution.started_at or execution.created_at)).total_seconds(),
        )
        await self.event_bus.emit(event)

        # Update metrics
        self._update_metrics(execution.workspace_id, timeouts=1)

    async def record_node_timeout(
        self,
        session: AsyncSession,
        node_execution: NodeExecution,
        execution: WorkflowExecution,
        timeout_percentage: float,
    ) -> None:
        """Record node timeout event and metrics.

        Args:
            session: Database session.
            node_execution: Timed out node.
            execution: Parent execution.
            timeout_percentage: Percentage of timeout used.
        """
        event = TimeoutEvent(
            event_type=TimeoutEventType.node_timeout,
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
            node_id=node_execution.node_id,
            reason="node_exceeded_timeout",
            timeout_seconds=node_execution.timeout_seconds,
            elapsed_seconds=(node_execution.completed_at or datetime.now(
                timezone.utc) - (node_execution.started_at or node_execution.created_at)).total_seconds(),
        )
        await self.event_bus.emit(event)

        # Update metrics
        metrics = self._metrics.get(execution.workspace_id)
        if metrics:
            metrics.node_timeouts += 1

    async def record_timeout_warning(
        self,
        execution: WorkflowExecution,
        timeout_percentage: float,
    ) -> None:
        """Record timeout warning event.

        Args:
            execution: Execution approaching timeout.
            timeout_percentage: Percentage of timeout consumed.
        """
        event = TimeoutEvent(
            event_type=TimeoutEventType.execution_timeout_warning,
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
            reason=f"execution_approaching_timeout_{timeout_percentage:.0f}%",
        )
        await self.event_bus.emit(event)

    async def record_cancellation(
        self,
        execution: WorkflowExecution,
        reason: str,
    ) -> None:
        """Record cancellation event.

        Args:
            execution: Cancelled execution.
            reason: Cancellation reason.
        """
        event = TimeoutEvent(
            event_type=TimeoutEventType.cancellation_initiated,
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
            reason=reason,
        )
        await self.event_bus.emit(event)

        # Update metrics
        self._update_metrics(execution.workspace_id, cancellations=1)

    async def record_cancellation_completed(
        self,
        execution: WorkflowExecution,
    ) -> None:
        """Record cancellation completion event.

        Args:
            execution: Cancelled execution.
        """
        event = TimeoutEvent(
            event_type=TimeoutEventType.cancellation_completed,
            workspace_id=execution.workspace_id,
            execution_id=execution.id,
        )
        await self.event_bus.emit(event)

    async def record_recovery_from_timeout(
        self,
        execution: WorkflowExecution,
    ) -> None:
        """Record successful recovery from timeout.

        Args:
            execution: Recovered execution.
        """
        metrics = self._metrics.get(execution.workspace_id)
        if metrics:
            metrics.recovered_from_timeout += 1

    def get_metrics(self, workspace_id: int) -> TimeoutMetrics:
        """Get current metrics for workspace.

        Args:
            workspace_id: Workspace ID.

        Returns:
            Current timeout metrics.
        """
        if workspace_id not in self._metrics:
            self._metrics[workspace_id] = TimeoutMetrics(
                workspace_id=workspace_id)
        return self._metrics[workspace_id]

    def _update_metrics(
        self,
        workspace_id: int,
        timeouts: int = 0,
        cancellations: int = 0,
        executions: int = 0,
    ) -> None:
        """Update metrics counters.

        Args:
            workspace_id: Workspace ID.
            timeouts: Number of timeouts to add.
            cancellations: Number of cancellations to add.
            executions: Number of executions to add.
        """
        if workspace_id not in self._metrics:
            self._metrics[workspace_id] = TimeoutMetrics(
                workspace_id=workspace_id)

        metrics = self._metrics[workspace_id]
        metrics.total_timeouts += timeouts
        metrics.total_cancellations += cancellations
        metrics.total_executions += executions


# Global metrics collector instance
_metrics_collector: Optional[WorkflowTimeoutMetricsCollector] = None


def get_metrics_collector() -> WorkflowTimeoutMetricsCollector:
    """Get or create global metrics collector.

    Returns:
        Global metrics collector instance.
    """
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = WorkflowTimeoutMetricsCollector()
    return _metrics_collector


def initialize_metrics_collector(
    event_bus: Optional[WorkflowTimeoutEventBus] = None,
) -> WorkflowTimeoutMetricsCollector:
    """Initialize global metrics collector.

    Args:
        event_bus: Optional event bus to use.

    Returns:
        Initialized metrics collector.
    """
    global _metrics_collector
    _metrics_collector = WorkflowTimeoutMetricsCollector(event_bus)
    return _metrics_collector
