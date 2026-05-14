"""
Workflow graph cycle detection and validation.

Detects cycles, orphan nodes, unreachable nodes, and invalid control flow patterns.
Uses DFS/BFS algorithms for graph analysis.
"""

from dataclasses import dataclass
from enum import Enum
from typing import Optional, Set, List, Dict, Tuple

from app.models.workflow import NodeType, WorkflowDefinition, WorkflowNode, WorkflowEdge


class ValidationErrorType(str, Enum):
    """Types of workflow graph validation errors."""

    cycle_detected = "cycle_detected"
    orphan_node = "orphan_node"
    unreachable_node = "unreachable_node"
    no_trigger_node = "no_trigger_node"
    multiple_triggers = "multiple_triggers"
    invalid_join = "invalid_join"
    invalid_split = "invalid_split"
    orphan_join = "orphan_join"
    orphan_split = "orphan_split"
    max_depth_exceeded = "max_depth_exceeded"
    invalid_edge = "invalid_edge"
    self_loop = "self_loop"


@dataclass
class ValidationError:
    """Graph validation error with details."""

    error_type: ValidationErrorType
    message: str
    node_ids: List[str]
    details: Dict = None

    def __post_init__(self):
        if self.details is None:
            self.details = {}

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "error_type": self.error_type.value,
            "message": self.message,
            "node_ids": self.node_ids,
            "details": self.details,
        }


@dataclass
class GraphValidationResult:
    """Result of workflow graph validation."""

    is_valid: bool
    errors: List[ValidationError]
    warnings: List[str]
    max_depth: int
    node_count: int
    edge_count: int
    trigger_nodes: List[str]
    cyclic_paths: List[List[str]]  # Paths that form cycles

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "is_valid": self.is_valid,
            "errors": [e.to_dict() for e in self.errors],
            "warnings": self.warnings,
            "max_depth": self.max_depth,
            "node_count": self.node_count,
            "edge_count": self.edge_count,
            "trigger_nodes": self.trigger_nodes,
            "cyclic_paths": self.cyclic_paths,
        }


class WorkflowGraphValidator:
    """Validates workflow graph structure and safety."""

    # Configuration
    MAX_TRAVERSAL_DEPTH = 1000  # Prevent stack overflow
    MAX_NODES = 10000  # Prevent memory issues
    MAX_EDGES = 50000
    MAX_EXECUTION_STEPS = 100000  # Max steps in single execution

    def __init__(self, max_depth: int = MAX_TRAVERSAL_DEPTH):
        """Initialize validator.

        Args:
            max_depth: Maximum allowed traversal depth.
        """
        self.max_depth = max_depth

    def validate_workflow(
        self,
        workflow: WorkflowDefinition,
    ) -> GraphValidationResult:
        """Validate complete workflow graph.

        Args:
            workflow: Workflow to validate.

        Returns:
            Validation result with errors and details.
        """
        errors: List[ValidationError] = []
        warnings: List[str] = []
        cyclic_paths: List[List[str]] = []

        # Build adjacency structures
        nodes_by_id = self._build_node_map(workflow.nodes)
        edges_by_source = self._build_edge_map(workflow.edges)

        # Check basic structure
        if not workflow.nodes:
            errors.append(
                ValidationError(
                    error_type=ValidationErrorType.no_trigger_node,
                    message="Workflow has no nodes",
                    node_ids=[],
                )
            )
            return GraphValidationResult(
                is_valid=False,
                errors=errors,
                warnings=warnings,
                max_depth=0,
                node_count=0,
                edge_count=0,
                trigger_nodes=[],
                cyclic_paths=[],
            )

        # Check size limits
        if len(workflow.nodes) > self.MAX_NODES:
            errors.append(
                ValidationError(
                    error_type=ValidationErrorType.invalid_edge,
                    message=f"Workflow exceeds max nodes ({self.MAX_NODES})",
                    node_ids=[],
                    details={"count": len(workflow.nodes),
                             "max": self.MAX_NODES},
                )
            )

        if len(workflow.edges) > self.MAX_EDGES:
            errors.append(
                ValidationError(
                    error_type=ValidationErrorType.invalid_edge,
                    message=f"Workflow exceeds max edges ({self.MAX_EDGES})",
                    node_ids=[],
                    details={"count": len(workflow.edges),
                             "max": self.MAX_EDGES},
                )
            )

        # Check for trigger nodes
        trigger_nodes = [
            n.node_id for n in workflow.nodes if n.node_type == NodeType.trigger
        ]

        if not trigger_nodes:
            errors.append(
                ValidationError(
                    error_type=ValidationErrorType.no_trigger_node,
                    message="Workflow has no trigger node",
                    node_ids=[],
                )
            )

        if len(trigger_nodes) > 1:
            warnings.append(f"Workflow has multiple triggers: {trigger_nodes}")

        # Check for self-loops
        for edge in workflow.edges:
            if edge.source_node_id == edge.target_node_id:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.self_loop,
                        message=f"Self-loop detected on node {edge.source_node_id}",
                        node_ids=[edge.source_node_id],
                        details={"edge_id": edge.edge_id},
                    )
                )

        # Check for invalid edges (referencing non-existent nodes)
        for edge in workflow.edges:
            if edge.source_node_id not in nodes_by_id:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.invalid_edge,
                        message=f"Edge references non-existent source node: {edge.source_node_id}",
                        node_ids=[edge.source_node_id],
                        details={"edge_id": edge.edge_id},
                    )
                )
            if edge.target_node_id not in nodes_by_id:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.invalid_edge,
                        message=f"Edge references non-existent target node: {edge.target_node_id}",
                        node_ids=[edge.target_node_id],
                        details={"edge_id": edge.edge_id},
                    )
                )

        # Check for cycles
        cycle_errors, cycles = self._detect_cycles(
            nodes_by_id, edges_by_source
        )
        errors.extend(cycle_errors)
        cyclic_paths.extend(cycles)

        # Check for orphan nodes (not connected to anything)
        orphan_errors = self._detect_orphan_nodes(
            nodes_by_id, workflow.edges
        )
        errors.extend(orphan_errors)

        # Check for unreachable nodes
        unreachable_errors, max_depth = self._detect_unreachable_nodes(
            nodes_by_id, edges_by_source, trigger_nodes
        )
        errors.extend(unreachable_errors)

        # Check max depth limit
        if max_depth > self.max_depth:
            errors.append(
                ValidationError(
                    error_type=ValidationErrorType.max_depth_exceeded,
                    message=f"Workflow depth exceeds limit ({max_depth} > {self.max_depth})",
                    node_ids=[],
                    details={"max_depth": max_depth, "limit": self.max_depth},
                )
            )

        # Check join/split validity
        join_split_errors = self._validate_joins_and_splits(
            nodes_by_id, edges_by_source
        )
        errors.extend(join_split_errors)

        is_valid = len(errors) == 0

        return GraphValidationResult(
            is_valid=is_valid,
            errors=errors,
            warnings=warnings,
            max_depth=max_depth,
            node_count=len(workflow.nodes),
            edge_count=len(workflow.edges),
            trigger_nodes=trigger_nodes,
            cyclic_paths=cyclic_paths,
        )

    def _build_node_map(
        self, nodes: List[WorkflowNode]
    ) -> Dict[str, WorkflowNode]:
        """Build map of node_id -> node."""
        return {node.node_id: node for node in nodes}

    def _build_edge_map(
        self, edges: List[WorkflowEdge]
    ) -> Dict[str, List[str]]:
        """Build adjacency map: source_node_id -> [target_node_ids]."""
        edge_map: Dict[str, List[str]] = {}
        for edge in edges:
            if edge.source_node_id not in edge_map:
                edge_map[edge.source_node_id] = []
            edge_map[edge.source_node_id].append(edge.target_node_id)
        return edge_map

    def _detect_cycles(
        self,
        nodes_by_id: Dict[str, WorkflowNode],
        edges_by_source: Dict[str, List[str]],
    ) -> Tuple[List[ValidationError], List[List[str]]]:
        """Detect cycles using DFS.

        Args:
            nodes_by_id: Map of node IDs to nodes.
            edges_by_source: Adjacency map.

        Returns:
            Tuple of (errors, cyclic_paths).
        """
        errors: List[ValidationError] = []
        cyclic_paths: List[List[str]] = []

        visited: Set[str] = set()
        rec_stack: Set[str] = set()
        paths: Dict[str, List[str]] = {}

        def dfs(node_id: str, path: List[str]) -> None:
            """DFS to detect cycles."""
            visited.add(node_id)
            rec_stack.add(node_id)
            path = path + [node_id]
            paths[node_id] = path

            for neighbor in edges_by_source.get(node_id, []):
                if neighbor not in visited:
                    dfs(neighbor, path)
                elif neighbor in rec_stack:
                    # Cycle detected
                    cycle_start_idx = path.index(neighbor)
                    cycle_path = path[cycle_start_idx:] + [neighbor]
                    cyclic_paths.append(cycle_path)
                    errors.append(
                        ValidationError(
                            error_type=ValidationErrorType.cycle_detected,
                            message=f"Cycle detected: {' -> '.join(cycle_path)}",
                            node_ids=cycle_path,
                            details={"cycle_path": cycle_path},
                        )
                    )

            rec_stack.discard(node_id)

        # Start DFS from all unvisited nodes
        for node_id in nodes_by_id.keys():
            if node_id not in visited:
                dfs(node_id, [])

        return errors, cyclic_paths

    def _detect_orphan_nodes(
        self,
        nodes_by_id: Dict[str, WorkflowNode],
        edges: List[WorkflowEdge],
    ) -> List[ValidationError]:
        """Detect nodes not connected to any edge.

        Args:
            nodes_by_id: Map of node IDs to nodes.
            edges: List of workflow edges.

        Returns:
            List of errors for orphan nodes.
        """
        errors: List[ValidationError] = []

        # Collect all nodes involved in edges
        connected_nodes: Set[str] = set()
        for edge in edges:
            connected_nodes.add(edge.source_node_id)
            connected_nodes.add(edge.target_node_id)

        # Orphan nodes are those not in any edge, except triggers can be alone
        for node_id, node in nodes_by_id.items():
            if (
                node_id not in connected_nodes
                and node.node_type != NodeType.trigger
            ):
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.orphan_node,
                        message=f"Node {node_id} is not connected to any edge",
                        node_ids=[node_id],
                        details={"node_type": node.node_type.value},
                    )
                )

        return errors

    def _detect_unreachable_nodes(
        self,
        nodes_by_id: Dict[str, WorkflowNode],
        edges_by_source: Dict[str, List[str]],
        trigger_nodes: List[str],
    ) -> Tuple[List[ValidationError], int]:
        """Detect nodes unreachable from trigger nodes using BFS.

        Args:
            nodes_by_id: Map of node IDs to nodes.
            edges_by_source: Adjacency map.
            trigger_nodes: List of trigger node IDs.

        Returns:
            Tuple of (errors, max_depth).
        """
        errors: List[ValidationError] = []
        reachable: Set[str] = set()
        max_depth = 0

        if not trigger_nodes:
            return errors, max_depth

        # BFS from all trigger nodes
        for trigger in trigger_nodes:
            queue: List[Tuple[str, int]] = [(trigger, 0)]
            visited_in_bfs: Set[str] = set()

            while queue:
                node_id, depth = queue.pop(0)
                max_depth = max(max_depth, depth)

                if node_id in visited_in_bfs:
                    continue

                visited_in_bfs.add(node_id)
                reachable.add(node_id)

                if depth > self.max_depth:
                    break

                for neighbor in edges_by_source.get(node_id, []):
                    if neighbor not in visited_in_bfs:
                        queue.append((neighbor, depth + 1))

        # Find unreachable nodes
        for node_id in nodes_by_id.keys():
            if node_id not in reachable:
                errors.append(
                    ValidationError(
                        error_type=ValidationErrorType.unreachable_node,
                        message=f"Node {node_id} is unreachable from trigger nodes",
                        node_ids=[node_id],
                        details={
                            "node_type": nodes_by_id[node_id].node_type.value},
                    )
                )

        return errors, max_depth

    def _validate_joins_and_splits(
        self,
        nodes_by_id: Dict[str, WorkflowNode],
        edges_by_source: Dict[str, List[str]],
    ) -> List[ValidationError]:
        """Validate join and split node configurations.

        Args:
            nodes_by_id: Map of node IDs to nodes.
            edges_by_source: Adjacency map.

        Returns:
            List of validation errors.
        """
        errors: List[ValidationError] = []

        # Build reverse map for incoming edges
        edges_by_target: Dict[str, List[str]] = {}
        for source_id, targets in edges_by_source.items():
            for target_id in targets:
                if target_id not in edges_by_target:
                    edges_by_target[target_id] = []
                edges_by_target[target_id].append(source_id)

        # Check split nodes (should have multiple outgoing edges)
        for node_id, node in nodes_by_id.items():
            if node.node_type == NodeType.split:
                outgoing = len(edges_by_source.get(node_id, []))
                if outgoing < 2:
                    errors.append(
                        ValidationError(
                            error_type=ValidationErrorType.invalid_split,
                            message=f"Split node {node_id} must have at least 2 outgoing edges (has {outgoing})",
                            node_ids=[node_id],
                            details={"outgoing_edges": outgoing},
                        )
                    )

            # Check join nodes (should have multiple incoming edges)
            elif node.node_type == NodeType.join:
                incoming = len(edges_by_target.get(node_id, []))
                if incoming < 2:
                    errors.append(
                        ValidationError(
                            error_type=ValidationErrorType.invalid_join,
                            message=f"Join node {node_id} must have at least 2 incoming edges (has {incoming})",
                            node_ids=[node_id],
                            details={"incoming_edges": incoming},
                        )
                    )

            # Check orphan joins/splits
            elif node.node_type in (NodeType.split, NodeType.join):
                outgoing = len(edges_by_source.get(node_id, []))
                incoming = len(edges_by_target.get(node_id, []))

                if outgoing == 0 and incoming == 0:
                    errors.append(
                        ValidationError(
                            error_type=ValidationErrorType.orphan_split
                            if node.node_type == NodeType.split
                            else ValidationErrorType.orphan_join,
                            message=f"Orphan {node.node_type.value} node {node_id} with no connections",
                            node_ids=[node_id],
                        )
                    )

        return errors

    def check_execution_safety(
        self,
        max_steps: Optional[int] = None,
        max_depth: Optional[int] = None,
    ) -> Dict[str, int]:
        """Check execution safety parameters.

        Args:
            max_steps: Maximum execution steps allowed.
            max_depth: Maximum traversal depth allowed.

        Returns:
            Dict with safety parameters.
        """
        max_steps = max_steps or self.MAX_EXECUTION_STEPS
        max_depth = max_depth or self.max_depth

        return {
            "max_execution_steps": max_steps,
            "max_traversal_depth": max_depth,
            "step_limit_exceeded_threshold": int(max_steps * 0.9),
            "depth_limit_exceeded_threshold": int(max_depth * 0.9),
        }
