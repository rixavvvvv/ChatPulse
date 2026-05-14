"""
Tests for workflow graph cycle detection and traversal safety.

Covers:
- Cyclic graph detection
- Malformed graph detection
- Deeply nested workflow handling
- Traversal safety monitoring
- Validation error reporting
"""

import pytest
from typing import List

from app.models.workflow import (
    NodeType,
    WorkflowNode,
    WorkflowEdge,
    WorkflowDefinition,
)
from app.services.workflow_graph_validator import (
    WorkflowGraphValidator,
    ValidationErrorType,
    GraphValidationResult,
)
from app.services.workflow_traversal_safety import (
    ExecutionTraversalMonitor,
    ExecutionStepLimitExceededError,
    TraversalDepthLimitExceededError,
    get_traversal_registry,
)


class MockWorkflowNode:
    """Mock WorkflowNode for testing."""

    def __init__(self, node_id: str, node_type: NodeType, name: str = ""):
        self.node_id = node_id
        self.node_type = node_type
        self.name = name or node_id
        self.config = {}


class MockWorkflowEdge:
    """Mock WorkflowEdge for testing."""

    def __init__(
        self,
        edge_id: str,
        source_node_id: str,
        target_node_id: str,
    ):
        self.edge_id = edge_id
        self.source_node_id = source_node_id
        self.target_node_id = target_node_id
        self.condition = None


class MockWorkflowDefinition:
    """Mock WorkflowDefinition for testing."""

    def __init__(self, nodes: List[MockWorkflowNode], edges: List[MockWorkflowEdge]):
        self.nodes = nodes
        self.edges = edges


class TestWorkflowGraphValidator:
    """Test workflow graph validation."""

    def test_valid_linear_workflow(self):
        """Test validation of valid linear workflow."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "action1"),
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True
        assert len(result.errors) == 0
        assert len(result.cyclic_paths) == 0

    def test_detect_simple_cycle(self):
        """Test detection of simple cycle."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
            MockWorkflowNode("action2", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "action1"),
            MockWorkflowEdge("edge2", "action1", "action2"),
            MockWorkflowEdge("edge3", "action2", "action1"),  # Cycle back
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        cycle_errors = [e for e in result.errors if e.error_type ==
                        ValidationErrorType.cycle_detected]
        assert len(cycle_errors) > 0
        assert len(result.cyclic_paths) > 0

    def test_detect_self_loop(self):
        """Test detection of self-loop."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "action1"),
            MockWorkflowEdge("edge2", "action1", "action1"),  # Self-loop
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        self_loop_errors = [
            e for e in result.errors if e.error_type == ValidationErrorType.self_loop]
        assert len(self_loop_errors) > 0

    def test_detect_orphan_nodes(self):
        """Test detection of orphan nodes."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
            # Not connected
            MockWorkflowNode("orphan_action", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "action1"),
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        orphan_errors = [
            e for e in result.errors if e.error_type == ValidationErrorType.orphan_node]
        assert len(orphan_errors) > 0

    def test_detect_unreachable_nodes(self):
        """Test detection of unreachable nodes."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
            MockWorkflowNode("unreachable_action", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "action1"),
            # unreachable_action has no incoming edge from reachable nodes
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        unreachable_errors = [
            e for e in result.errors if e.error_type == ValidationErrorType.unreachable_node]
        assert len(unreachable_errors) > 0

    def test_detect_no_trigger_node(self):
        """Test detection of missing trigger node."""
        nodes = [
            MockWorkflowNode("action1", NodeType.action),
        ]
        edges = []
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        no_trigger_errors = [
            e for e in result.errors if e.error_type == ValidationErrorType.no_trigger_node]
        assert len(no_trigger_errors) > 0

    def test_detect_invalid_split(self):
        """Test detection of invalid split node (must have 2+ outgoing edges)."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("split1", NodeType.split),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "split1"),
            # split1 has no outgoing edges - invalid
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        split_errors = [e for e in result.errors if e.error_type ==
                        ValidationErrorType.invalid_split]
        assert len(split_errors) > 0

    def test_detect_invalid_join(self):
        """Test detection of invalid join node (must have 2+ incoming edges)."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("join1", NodeType.join),
            MockWorkflowNode("action1", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "join1"),
            # join1 has only 1 incoming edge - invalid
            MockWorkflowEdge("edge2", "join1", "action1"),
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        join_errors = [e for e in result.errors if e.error_type ==
                       ValidationErrorType.invalid_join]
        assert len(join_errors) > 0

    def test_detect_invalid_edge_target(self):
        """Test detection of edge referencing non-existent target node."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
        ]
        edges = [
            MockWorkflowEdge("edge1", "trigger1", "nonexistent_node"),
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        invalid_edge_errors = [
            e for e in result.errors if e.error_type == ValidationErrorType.invalid_edge]
        assert len(invalid_edge_errors) > 0

    def test_complex_valid_workflow(self):
        """Test validation of complex valid workflow with splits and joins."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
            MockWorkflowNode("split1", NodeType.split),
            MockWorkflowNode("action2", NodeType.action),
            MockWorkflowNode("action3", NodeType.action),
            MockWorkflowNode("join1", NodeType.join),
            MockWorkflowNode("action4", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("e1", "trigger1", "action1"),
            MockWorkflowEdge("e2", "action1", "split1"),
            MockWorkflowEdge("e3", "split1", "action2"),
            MockWorkflowEdge("e4", "split1", "action3"),
            MockWorkflowEdge("e5", "action2", "join1"),
            MockWorkflowEdge("e6", "action3", "join1"),
            MockWorkflowEdge("e7", "join1", "action4"),
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True
        assert len(result.errors) == 0

    def test_deeply_nested_workflow(self):
        """Test validation of deeply nested workflow."""
        # Create a deep chain of nodes
        nodes = [MockWorkflowNode("trigger1", NodeType.trigger)]
        edges = []

        for i in range(1, 50):
            nodes.append(MockWorkflowNode(f"action{i}", NodeType.action))
            edges.append(MockWorkflowEdge(
                f"edge{i}", f"action{i-1}", f"action{i}"))

        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is True
        assert result.max_depth >= 49

    def test_max_depth_limit_exceeded(self):
        """Test detection of max depth limit exceeded."""
        # Create a workflow exceeding max depth
        max_depth = 10
        validator = WorkflowGraphValidator(max_depth=max_depth)

        nodes = [MockWorkflowNode("trigger1", NodeType.trigger)]
        edges = []

        # Create chain deeper than max_depth
        for i in range(1, max_depth + 5):
            nodes.append(MockWorkflowNode(f"action{i}", NodeType.action))
            edges.append(MockWorkflowEdge(
                f"edge{i}", f"action{i-1}", f"action{i}"))

        workflow = MockWorkflowDefinition(nodes, edges)
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        depth_errors = [e for e in result.errors if e.error_type ==
                        ValidationErrorType.max_depth_exceeded]
        assert len(depth_errors) > 0


class TestExecutionTraversalMonitor:
    """Test execution traversal safety monitoring."""

    def test_step_limit_enforcement(self):
        """Test that step limit is enforced."""
        monitor = ExecutionTraversalMonitor(
            execution_id="test_exec",
            max_steps=10,
            max_depth=100,
        )

        # Should succeed up to max_steps
        for i in range(10):
            monitor.increment_step()

        # Should fail on max_steps + 1
        with pytest.raises(ExecutionStepLimitExceededError):
            monitor.increment_step()

    def test_depth_limit_enforcement(self):
        """Test that depth limit is enforced."""
        monitor = ExecutionTraversalMonitor(
            execution_id="test_exec",
            max_steps=100,
            max_depth=10,
        )

        # Should succeed up to max_depth
        for i in range(10):
            monitor.enter_node(f"node_{i}", i)

        # Should fail on depth > max_depth
        with pytest.raises(TraversalDepthLimitExceededError):
            monitor.enter_node("node_fail", 11)

    def test_warning_thresholds(self):
        """Test warning threshold detection."""
        monitor = ExecutionTraversalMonitor(
            execution_id="test_exec",
            max_steps=100,
            max_depth=100,
            warning_threshold=0.8,
        )

        # Should not trigger warning at 79 steps
        for i in range(79):
            monitor.increment_step()
        assert monitor.is_near_step_limit() is False

        # Should trigger warning at 80 steps (80% of 100)
        monitor.increment_step()
        assert monitor.is_near_step_limit() is True

    def test_path_tracking_for_loop_detection(self):
        """Test path tracking for loop detection."""
        monitor = ExecutionTraversalMonitor(
            execution_id="test_exec",
            max_steps=1000,
            max_depth=100,
        )

        # Record path multiple times
        path = ("node1", "node2", "node3")
        monitor.record_path(path)
        assert monitor.loop_warning_triggered is False

        # Record same path again - should trigger loop warning
        monitor.record_path(path)
        assert monitor.loop_warning_triggered is True

    def test_traversal_stats(self):
        """Test collection of traversal statistics."""
        monitor = ExecutionTraversalMonitor(
            execution_id="test_exec",
            max_steps=1000,
            max_depth=100,
        )

        # Execute some steps
        for i in range(50):
            monitor.increment_step()
            monitor.enter_node(f"node_{i}", i % 10)

        stats = monitor.get_stats()

        assert stats.execution_id == "test_exec"
        assert stats.step_count == 50
        assert stats.max_depth_reached >= 9
        assert stats.nodes_visited >= 10

    def test_traversal_registry(self):
        """Test traversal monitor registry."""
        registry = get_traversal_registry()

        # Create monitors
        monitor1 = registry.create_monitor(
            "exec1", max_steps=100, max_depth=50)
        monitor2 = registry.create_monitor(
            "exec2", max_steps=200, max_depth=100)

        assert registry.get_monitor("exec1") is monitor1
        assert registry.get_monitor("exec2") is monitor2

        # Get all monitors
        all_monitors = registry.get_all_monitors()
        assert len(all_monitors) >= 2

        # Remove monitor
        registry.remove_monitor("exec1")
        assert registry.get_monitor("exec1") is None


class TestComplexGraphScenarios:
    """Test complex real-world graph scenarios."""

    def test_multiple_cycles(self):
        """Test detection of multiple independent cycles."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("action1", NodeType.action),
            MockWorkflowNode("action2", NodeType.action),
            MockWorkflowNode("action3", NodeType.action),
            MockWorkflowNode("action4", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("e1", "trigger1", "action1"),
            # Cycle 1: action1 -> action2 -> action1
            MockWorkflowEdge("e2", "action1", "action2"),
            MockWorkflowEdge("e3", "action2", "action1"),
            # Cycle 2: action3 -> action4 -> action3
            MockWorkflowEdge("e4", "action1", "action3"),
            MockWorkflowEdge("e5", "action3", "action4"),
            MockWorkflowEdge("e6", "action4", "action3"),
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        cycle_errors = [e for e in result.errors if e.error_type ==
                        ValidationErrorType.cycle_detected]
        assert len(cycle_errors) >= 2

    def test_branching_with_multiple_cycles(self):
        """Test complex branching with multiple cycles."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("split1", NodeType.split),
            MockWorkflowNode("action1", NodeType.action),
            MockWorkflowNode("action2", NodeType.action),
            MockWorkflowNode("loop1", NodeType.action),
            MockWorkflowNode("loop2", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("e1", "trigger1", "split1"),
            MockWorkflowEdge("e2", "split1", "action1"),
            MockWorkflowEdge("e3", "split1", "action2"),
            MockWorkflowEdge("e4", "action1", "loop1"),
            MockWorkflowEdge("e5", "loop1", "action1"),  # Cycle
            MockWorkflowEdge("e6", "action2", "loop2"),
            MockWorkflowEdge("e7", "loop2", "action2"),  # Cycle
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False

    def test_malformed_split_join_pairs(self):
        """Test detection of mismatched split/join pairs."""
        nodes = [
            MockWorkflowNode("trigger1", NodeType.trigger),
            MockWorkflowNode("split1", NodeType.split),
            MockWorkflowNode("action1", NodeType.action),
            MockWorkflowNode("action2", NodeType.action),
            MockWorkflowNode("split2", NodeType.split),
            MockWorkflowNode("join1", NodeType.join),
        ]
        edges = [
            MockWorkflowEdge("e1", "trigger1", "split1"),
            MockWorkflowEdge("e2", "split1", "action1"),
            MockWorkflowEdge("e3", "split1", "action2"),
            MockWorkflowEdge("e4", "action1", "split2"),
            MockWorkflowEdge("e5", "split2", "join1"),
            # Missing connection from action2
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False

    def test_all_nodes_in_cycle(self):
        """Test detection when all nodes form a single cycle."""
        nodes = [
            MockWorkflowNode("node1", NodeType.trigger),
            MockWorkflowNode("node2", NodeType.action),
            MockWorkflowNode("node3", NodeType.action),
        ]
        edges = [
            MockWorkflowEdge("e1", "node1", "node2"),
            MockWorkflowEdge("e2", "node2", "node3"),
            MockWorkflowEdge("e3", "node3", "node1"),  # Complete cycle
        ]
        workflow = MockWorkflowDefinition(nodes, edges)

        validator = WorkflowGraphValidator()
        result = validator.validate_workflow(workflow)

        assert result.is_valid is False
        cycle_errors = [e for e in result.errors if e.error_type ==
                        ValidationErrorType.cycle_detected]
        assert len(cycle_errors) > 0


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
