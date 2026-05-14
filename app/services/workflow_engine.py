import asyncio
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import Settings
from app.models.workflow import (
    ExecutionStatus,
    NodeExecution,
    NodeType,
    WorkflowDefinition,
    WorkflowEdge,
    WorkflowExecution,
    WorkflowNode,
)
from app.services import workflow_service
from app.services.expression_evaluator import (
    ExpressionEvaluator,
    ExpressionSyntaxError,
    ExpressionEvaluationError,
    get_metrics,
)
from app.services.workflow_timeout_service import WorkflowTimeoutService
from app.services.workflow_cancellation_service import WorkflowCancellationService
from app.services.workflow_traversal_safety import (
    ExecutionTraversalMonitor,
    get_traversal_registry,
    ExecutionStepLimitExceededError,
    TraversalDepthLimitExceededError,
)

logger = logging.getLogger(__name__)


class WorkflowTraversalEngine:
    def __init__(self, db: AsyncSession, settings: Settings):
        self.db = db
        self.settings = settings
        self._node_handlers: dict[NodeType, Callable] = {}
        self._expression_evaluator = ExpressionEvaluator()
        self.timeout_service = WorkflowTimeoutService(settings)
        self.cancellation_service = WorkflowCancellationService()
        self._register_default_handlers()

    def _register_default_handlers(self):
        self._node_handlers = {
            NodeType.trigger: self._handle_trigger,
            NodeType.action: self._handle_action,
            NodeType.condition: self._handle_condition,
            NodeType.delay: self._handle_delay,
            NodeType.split: self._handle_split,
            NodeType.join: self._handle_join,
        }

    def register_handler(self, node_type: NodeType, handler: Callable):
        self._node_handlers[node_type] = handler

    async def execute_workflow(
        self,
        execution: WorkflowExecution,
        workflow: WorkflowDefinition,
    ) -> WorkflowExecution:
        nodes = {n.node_id: n for n in workflow.nodes}
        edges = {e.edge_id: e for e in workflow.edges}
        adjacency = self._build_adjacency_list(workflow.edges)

        start_nodes = [
            n for n in workflow.nodes if n.node_type == NodeType.trigger]
        if not start_nodes:
            await workflow_service.update_execution(
                self.db,
                execution,
                status=ExecutionStatus.failed,
                error="No trigger node found",
                completed_at=datetime.now(timezone.utc),
            )
            return execution

        # Create traversal safety monitor
        registry = get_traversal_registry()
        traversal_monitor = registry.create_monitor(
            execution.execution_id,
            max_steps=100000,
            max_depth=1000,
        )

        # Compute execution timeout deadline
        execution.timeout_at = self.timeout_service.compute_execution_timeout_deadline(
            execution,
            self.settings,
        )
        if execution.timeout_seconds is None and execution.definition:
            execution.timeout_seconds = (
                execution.definition.timeout_seconds
                or self.settings.workflow_execution_timeout_seconds
            )

        await workflow_service.update_execution(
            self.db,
            execution,
            status=ExecutionStatus.running,
            started_at=datetime.now(timezone.utc),
        )

        current_node_id = start_nodes[0].node_id
        current_depth = 0
        current_path = []

        try:
            while current_node_id and current_node_id in nodes:
                # Traversal safety checks
                try:
                    traversal_monitor.increment_step()
                    traversal_monitor.enter_node(
                        current_node_id, current_depth)
                except (ExecutionStepLimitExceededError, TraversalDepthLimitExceededError) as e:
                    logger.error(
                        f"Traversal limit exceeded: {e} in execution {execution.execution_id}"
                    )
                    await self.cancellation_service.cancel_execution(
                        self.db,
                        execution,
                        reason=f"traversal_limit_exceeded: {str(e)}",
                        propagate=True,
                    )
                    break

                # Check warnings
                if traversal_monitor.is_near_step_limit():
                    logger.warning(
                        f"Execution {execution.execution_id} approaching step limit: "
                        f"{traversal_monitor.step_count}/{traversal_monitor.max_steps}"
                    )

                if traversal_monitor.is_near_depth_limit():
                    logger.warning(
                        f"Execution {execution.execution_id} approaching depth limit: "
                        f"{traversal_monitor.current_depth}/{traversal_monitor.max_depth}"
                    )

                # Check if execution has timed out
                if self.timeout_service.is_execution_timed_out(execution):
                    logger.warning(
                        f"Workflow execution {execution.execution_id} timed out"
                    )
                    await self.cancellation_service.cancel_execution(
                        self.db,
                        execution,
                        reason="timeout",
                        propagate=True,
                    )
                    break

                node = nodes[current_node_id]

                await workflow_service.update_execution(
                    self.db,
                    execution,
                    current_node_id=current_node_id,
                )

                node_execution = await workflow_service.create_node_execution(
                    self.db,
                    execution.id,
                    node.node_id,
                    node.node_type.value,
                    {"context": execution.context.copy()},
                )

                # Set node timeout deadline
                node_execution.timeout_at = self.timeout_service.compute_node_timeout_deadline(
                    node_execution,
                    self.settings,
                )
                if node_execution.timeout_seconds is None:
                    node_execution.timeout_seconds = self.settings.workflow_node_timeout_seconds

                node_execution = await self._execute_node(
                    node_execution,
                    node,
                    execution,
                )

                next_node_id = await self._get_next_node(
                    node,
                    node_execution,
                    adjacency,
                    execution,
                )

                # Record path for loop detection
                current_path.append(current_node_id)
                if len(current_path) > 10:
                    traversal_monitor.record_path(tuple(current_path[-10:]))

                if not next_node_id:
                    break

                current_node_id = next_node_id
                current_depth += 1

            # Mark as completed only if not cancelled
            if execution.status != ExecutionStatus.cancelled:
                await workflow_service.update_execution(
                    self.db,
                    execution,
                    status=ExecutionStatus.completed,
                    completed_at=datetime.now(timezone.utc),
                )

        except asyncio.TimeoutError:
            logger.error(
                f"Workflow execution {execution.execution_id} exceeded timeout")
            await self.cancellation_service.cancel_execution(
                self.db,
                execution,
                reason="timeout",
                propagate=True,
            )
        except Exception as e:
            logger.exception(
                f"Workflow execution {execution.execution_id} failed")
            await workflow_service.update_execution(
                self.db,
                execution,
                status=ExecutionStatus.failed,
                error=str(e),
                completed_at=datetime.now(timezone.utc),
            )
        finally:
            # Log traversal statistics
            stats = traversal_monitor.get_stats()
            logger.info(
                f"Execution {execution.execution_id} traversal stats: {stats.to_dict()}")
            registry.remove_monitor(execution.execution_id)

        await self.db.commit()
        return execution

    async def _execute_node(
        self,
        node_execution: NodeExecution,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> NodeExecution:
        node_execution.status = ExecutionStatus.running
        node_execution.started_at = datetime.now(timezone.utc)
        await self.db.commit()

        try:
            # Compute time available for node execution
            execution_remaining = self.timeout_service.get_execution_time_remaining(
                execution)
            node_timeout = node_execution.timeout_seconds or self.settings.workflow_node_timeout_seconds

            # Use the smaller of node timeout and remaining execution time
            if execution_remaining and execution_remaining.total_seconds() > 0:
                effective_timeout = min(
                    node_timeout,
                    execution_remaining.total_seconds(),
                )
            else:
                effective_timeout = node_timeout

            handler = self._node_handlers.get(node.node_type)
            if not handler:
                raise ValueError(f"No handler for node type: {node.node_type}")

            # Execute with timeout protection
            try:
                result = await asyncio.wait_for(
                    handler(node, execution),
                    timeout=effective_timeout,
                )
            except asyncio.TimeoutError:
                logger.warning(
                    f"Node {node.node_id} timed out after {effective_timeout}s"
                )
                node_execution.status = ExecutionStatus.failed
                node_execution.error = f"Node execution timed out after {effective_timeout}s"
                node_execution.completed_at = datetime.now(timezone.utc)
                raise

            node_execution.status = ExecutionStatus.completed
            node_execution.output_data = result
            node_execution.completed_at = datetime.now(timezone.utc)

        except Exception as e:
            if node_execution.status != ExecutionStatus.failed:
                node_execution.status = ExecutionStatus.failed
                node_execution.error = str(e)
                node_execution.completed_at = datetime.now(timezone.utc)
            raise

        await self.db.commit()
        return node_execution

    async def _handle_trigger(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        config = node.config
        trigger_type = config.get("type", "manual")

        if trigger_type == "webhook":
            return {"received": True, "data": execution.trigger_data}
        elif trigger_type == "schedule":
            return {"scheduled": True, "next_run": config.get("cron")}
        else:
            return {"triggered": True, "source": "manual"}

    async def _handle_action(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        config = node.config
        action_type = config.get("action_type", "")
        parameters = config.get("parameters", {})

        execution.context[f"last_action"] = action_type
        execution.context[f"{action_type}_result"] = {"success": True}

        return {
            "action": action_type,
            "executed": True,
            "parameters": parameters,
            "context": execution.context.copy(),
        }

    async def _handle_condition(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        config = node.config
        expression = config.get("expression", "")

        result = self._evaluate_expression(expression, execution.context)

        execution.context["last_condition_result"] = result

        return {
            "expression": expression,
            "result": result,
            "path": "true" if result else "false",
        }

    async def _handle_delay(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        config = node.config
        duration = config.get("duration_seconds", 0)

        try:
            await asyncio.sleep(duration)
        except asyncio.CancelledError:
            logger.info(
                f"Delay node interrupted, can be resumed for workflow {execution.execution_id}"
            )
            raise

        return {
            "delayed": True,
            "duration_seconds": duration,
            "resumed_at": datetime.now(timezone.utc).isoformat(),
        }

    async def _handle_split(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        config = node.config
        branches = config.get("branches", [])
        distribution = config.get("distribution", "all")

        execution.context["active_branches"] = branches

        return {
            "branches": branches,
            "distribution": distribution,
            "spawned": len(branches),
        }

    async def _handle_join(
        self,
        node: WorkflowNode,
        execution: WorkflowExecution,
    ) -> dict[str, Any]:
        config = node.config
        wait_for = config.get("wait_for", [])

        active_branches = execution.context.get("active_branches", [])
        completed_branches = execution.context.get("completed_branches", [])

        return {
            "waiting_for": wait_for,
            "active": active_branches,
            "completed": completed_branches,
            "joined": True,
        }

    def _evaluate_expression(self, expression: str, context: dict[str, Any]) -> bool:
        """
        Safely evaluate a workflow condition expression.

        Uses AST-based evaluation to prevent code injection attacks.
        """
        try:
            return self._expression_evaluator.evaluate(expression, context)
        except ExpressionSyntaxError as e:
            logger.warning(f"Expression syntax error: {e}")
            return False
        except ExpressionEvaluationError as e:
            logger.warning(f"Expression evaluation error: {e}")
            return False
        except Exception as e:
            logger.exception(
                f"Unexpected error evaluating expression: {expression}")
            return False

    def _build_adjacency_list(self, edges: list[WorkflowEdge]) -> dict[str, list[str]]:
        adjacency: dict[str, list[str]] = {}
        for edge in edges:
            if edge.source_node_id not in adjacency:
                adjacency[edge.source_node_id] = []
            adjacency[edge.source_node_id].append(edge.target_node_id)
        return adjacency

    async def _get_next_node(
        self,
        current_node: WorkflowNode,
        node_execution: NodeExecution,
        adjacency: dict[str, list[str]],
        execution: WorkflowExecution,
    ) -> str | None:
        if current_node.node_type == NodeType.condition:
            result = node_execution.output_data.get("result", False)
            edges = [e for e in adjacency.get(current_node.node_id, [])]

            for target_id in edges:
                edge = next(
                    (e for e in execution.definition.edges if e.target_node_id == target_id), None)
                if edge and edge.condition:
                    condition_result = self._evaluate_expression(
                        edge.condition, execution.context)
                    if condition_result:
                        return target_id
                elif not edge or not edge.condition:
                    if result:
                        return target_id

            return None

        if current_node.node_type == NodeType.split:
            branches = node_execution.output_data.get("branches", [])
            return branches[0] if branches else None

        return adjacency.get(current_node.node_id, [None])[0]


async def start_workflow(
    db: AsyncSession,
    workflow: WorkflowDefinition,
    trigger_data: dict[str, Any],
) -> WorkflowExecution:
    execution = await workflow_service.create_execution(
        db,
        workflow.workspace_id,
        workflow.id,
        trigger_data,
    )

    engine = WorkflowTraversalEngine(db)
    await engine.execute_workflow(execution, workflow)

    return execution
