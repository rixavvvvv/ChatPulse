"""
Workflow execution traversal safety enforcement.

Monitors and enforces execution step limits and depth limits during runtime
to prevent infinite loops and worker starvation.
"""

from dataclasses import dataclass
from typing import Optional

from app.models.workflow import WorkflowExecution


class TraversalLimitExceededError(Exception):
    """Raised when traversal limit is exceeded."""

    pass


class ExecutionStepLimitExceededError(TraversalLimitExceededError):
    """Raised when execution step limit is exceeded."""

    pass


class TraversalDepthLimitExceededError(TraversalLimitExceededError):
    """Raised when traversal depth limit is exceeded."""

    pass


@dataclass
class ExecutionTraversalStats:
    """Statistics about execution traversal."""

    execution_id: str
    step_count: int
    max_depth_reached: int
    nodes_visited: int
    node_execution_count: int
    loop_detection_triggered: bool = False
    depth_warning_at: Optional[int] = None
    step_warning_at: Optional[int] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "execution_id": self.execution_id,
            "step_count": self.step_count,
            "max_depth_reached": self.max_depth_reached,
            "nodes_visited": self.nodes_visited,
            "node_execution_count": self.node_execution_count,
            "loop_detection_triggered": self.loop_detection_triggered,
            "depth_warning_at": self.depth_warning_at,
            "step_warning_at": self.step_warning_at,
        }


class ExecutionTraversalMonitor:
    """Monitors execution traversal for safety limits."""

    def __init__(
        self,
        execution_id: str,
        max_steps: int = 100000,
        max_depth: int = 1000,
        warning_threshold: float = 0.8,
    ):
        """Initialize traversal monitor.

        Args:
            execution_id: Execution being monitored.
            max_steps: Maximum execution steps allowed.
            max_depth: Maximum traversal depth allowed.
            warning_threshold: Warn when threshold% of limit reached (0.8 = 80%).
        """
        self.execution_id = execution_id
        self.max_steps = max_steps
        self.max_depth = max_depth
        self.warning_threshold = warning_threshold

        self.step_count = 0
        self.current_depth = 0
        self.max_depth_reached = 0
        self.visited_nodes = set()
        self.node_execution_count = 0
        # Track paths to detect loops
        self.visited_paths: dict[tuple, int] = {}

        self.step_warning_triggered = False
        self.depth_warning_triggered = False
        self.loop_warning_triggered = False

    def increment_step(self) -> None:
        """Increment execution step counter.

        Raises:
            ExecutionStepLimitExceededError: If step limit exceeded.
        """
        self.step_count += 1

        if self.step_count > self.max_steps:
            raise ExecutionStepLimitExceededError(
                f"Execution step limit exceeded: {self.step_count} > {self.max_steps}",
            )

        # Check warning threshold
        if not self.step_warning_triggered:
            warning_limit = int(self.max_steps * self.warning_threshold)
            if self.step_count >= warning_limit:
                self.step_warning_triggered = True

    def enter_node(self, node_id: str, current_depth: int) -> None:
        """Record node entry.

        Args:
            node_id: Node ID being entered.
            current_depth: Current traversal depth.

        Raises:
            TraversalDepthLimitExceededError: If depth limit exceeded.
        """
        self.current_depth = current_depth
        self.max_depth_reached = max(self.max_depth_reached, current_depth)
        self.visited_nodes.add(node_id)
        self.node_execution_count += 1

        if current_depth > self.max_depth:
            raise TraversalDepthLimitExceededError(
                f"Traversal depth limit exceeded: {current_depth} > {self.max_depth}",
            )

        # Check warning threshold
        if not self.depth_warning_triggered:
            warning_depth = int(self.max_depth * self.warning_threshold)
            if current_depth >= warning_depth:
                self.depth_warning_triggered = True

    def record_path(self, path: tuple) -> None:
        """Record execution path for loop detection.

        Args:
            path: Tuple of node IDs visited in current path.
        """
        if path not in self.visited_paths:
            self.visited_paths[path] = 0
        self.visited_paths[path] += 1

        # If path repeated 2+ times, likely a loop
        if self.visited_paths[path] > 1 and not self.loop_warning_triggered:
            self.loop_warning_triggered = True

    def is_near_step_limit(self) -> bool:
        """Check if approaching step limit.

        Returns:
            True if step count >= warning_threshold * max_steps.
        """
        warning_limit = int(self.max_steps * self.warning_threshold)
        return self.step_count >= warning_limit

    def is_near_depth_limit(self) -> bool:
        """Check if approaching depth limit.

        Returns:
            True if current_depth >= warning_threshold * max_depth.
        """
        warning_depth = int(self.max_depth * self.warning_threshold)
        return self.current_depth >= warning_depth

    def get_stats(self) -> ExecutionTraversalStats:
        """Get traversal statistics.

        Returns:
            Current traversal statistics.
        """
        return ExecutionTraversalStats(
            execution_id=self.execution_id,
            step_count=self.step_count,
            max_depth_reached=self.max_depth_reached,
            nodes_visited=len(self.visited_nodes),
            node_execution_count=self.node_execution_count,
            loop_detection_triggered=self.loop_warning_triggered,
            depth_warning_at=(
                int(self.max_depth * self.warning_threshold)
                if self.depth_warning_triggered
                else None
            ),
            step_warning_at=(
                int(self.max_steps * self.warning_threshold)
                if self.step_warning_triggered
                else None
            ),
        )

    def check_step_progress(self) -> dict:
        """Get step progress information.

        Returns:
            Dict with step count, max, and percentage.
        """
        percentage = (self.step_count / self.max_steps) * \
            100 if self.max_steps > 0 else 0
        return {
            "current": self.step_count,
            "max": self.max_steps,
            "percentage": percentage,
            "warning_triggered": self.step_warning_triggered,
        }

    def check_depth_progress(self) -> dict:
        """Get depth progress information.

        Returns:
            Dict with current depth, max, and percentage.
        """
        percentage = (
            (self.max_depth_reached / self.max_depth) *
            100 if self.max_depth > 0 else 0
        )
        return {
            "current": self.current_depth,
            "max": self.max_depth,
            "max_reached": self.max_depth_reached,
            "percentage": percentage,
            "warning_triggered": self.depth_warning_triggered,
        }


class ExecutionTraversalMonitorRegistry:
    """Registry of traversal monitors for active executions."""

    def __init__(self):
        """Initialize monitor registry."""
        self._monitors: dict[str, ExecutionTraversalMonitor] = {}

    def create_monitor(
        self,
        execution_id: str,
        max_steps: int = 100000,
        max_depth: int = 1000,
    ) -> ExecutionTraversalMonitor:
        """Create and register traversal monitor.

        Args:
            execution_id: Execution ID.
            max_steps: Maximum execution steps.
            max_depth: Maximum traversal depth.

        Returns:
            Created monitor.
        """
        monitor = ExecutionTraversalMonitor(
            execution_id=execution_id,
            max_steps=max_steps,
            max_depth=max_depth,
        )
        self._monitors[execution_id] = monitor
        return monitor

    def get_monitor(self, execution_id: str) -> Optional[ExecutionTraversalMonitor]:
        """Get traversal monitor for execution.

        Args:
            execution_id: Execution ID.

        Returns:
            Monitor or None if not found.
        """
        return self._monitors.get(execution_id)

    def remove_monitor(self, execution_id: str) -> None:
        """Remove traversal monitor for execution.

        Args:
            execution_id: Execution ID.
        """
        self._monitors.pop(execution_id, None)

    def get_all_monitors(self) -> dict[str, ExecutionTraversalMonitor]:
        """Get all active monitors.

        Returns:
            Dict of execution_id -> monitor.
        """
        return self._monitors.copy()

    def get_stats_for_all(self) -> dict[str, dict]:
        """Get stats for all active executions.

        Returns:
            Dict of execution_id -> stats.
        """
        return {
            exec_id: monitor.get_stats().to_dict()
            for exec_id, monitor in self._monitors.items()
        }


# Global registry instance
_traversal_registry: Optional[ExecutionTraversalMonitorRegistry] = None


def get_traversal_registry() -> ExecutionTraversalMonitorRegistry:
    """Get or create global traversal monitor registry.

    Returns:
        Global registry instance.
    """
    global _traversal_registry
    if _traversal_registry is None:
        _traversal_registry = ExecutionTraversalMonitorRegistry()
    return _traversal_registry
