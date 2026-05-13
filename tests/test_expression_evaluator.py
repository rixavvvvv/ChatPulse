"""
Tests for Safe Expression Evaluator

Covers:
- Basic operators (equals, not_equals, greater_than, less_than, contains, in_list)
- Logical operators (and, or, not)
- Nested conditions
- Malicious payloads
- Invalid syntax
- Performance
"""

import pytest
import time
from app.services.expression_evaluator import (
    ExpressionEvaluator,
    ExpressionSyntaxError,
    ExpressionEvaluationError,
    get_metrics,
    evaluate_expression,
    parse_and_validate,
)


class TestBasicOperators:
    """Test basic comparison and equality operators."""

    def test_equals_string(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status == 'active'", {"status": "active"}) is True
        assert evaluator.evaluate("status == 'active'", {"status": "inactive"}) is False

    def test_equals_number(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("priority == 5", {"priority": 5}) is True
        assert evaluator.evaluate("priority == 5", {"priority": 3}) is False

    def test_equals_boolean(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("is_active == True", {"is_active": True}) is True
        assert evaluator.evaluate("is_active == True", {"is_active": False}) is False

    def test_not_equals(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status != 'closed'", {"status": "open"}) is True
        assert evaluator.evaluate("status != 'closed'", {"status": "closed"}) is False

    def test_greater_than(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("priority > 5", {"priority": 10}) is True
        assert evaluator.evaluate("priority > 5", {"priority": 5}) is False
        assert evaluator.evaluate("priority > 5", {"priority": 3}) is False

    def test_less_than(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("count < 10", {"count": 5}) is True
        assert evaluator.evaluate("count < 10", {"count": 10}) is False
        assert evaluator.evaluate("count < 10", {"count": 15}) is False

    def test_greater_than_or_equal(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("priority >= 5", {"priority": 5}) is True
        assert evaluator.evaluate("priority >= 5", {"priority": 6}) is True
        assert evaluator.evaluate("priority >= 5", {"priority": 4}) is False

    def test_less_than_or_equal(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("count <= 10", {"count": 10}) is True
        assert evaluator.evaluate("count <= 10", {"count": 9}) is True
        assert evaluator.evaluate("count <= 10", {"count": 11}) is False

    def test_contains_string(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("'hello' in message", {"message": "hello world"}) is True
        assert evaluator.evaluate("'foo' in message", {"message": "hello world"}) is False

    def test_in_list(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status in ['open', 'pending']", {"status": "open"}) is True
        assert evaluator.evaluate("status in ['open', 'pending']", {"status": "closed"}) is False

    def test_in_tuple(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status in ('open', 'pending')", {"status": "pending"}) is True

    def test_not_in_list(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status not in ['closed', 'archived']", {"status": "open"}) is True
        assert evaluator.evaluate("status not in ['closed', 'archived']", {"status": "closed"}) is False


class TestLogicalOperators:
    """Test and/or/not logical operators."""

    def test_and_operator(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status == 'active' and priority > 5", {
            "status": "active",
            "priority": 10
        }) is True
        assert evaluator.evaluate("status == 'active' and priority > 5", {
            "status": "active",
            "priority": 3
        }) is False

    def test_or_operator(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("status == 'open' or status == 'pending'", {
            "status": "open"
        }) is True
        assert evaluator.evaluate("status == 'open' or status == 'pending'", {
            "status": "closed"
        }) is False

    def test_not_operator(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("not status == 'closed'", {"status": "open"}) is True
        assert evaluator.evaluate("not status == 'closed'", {"status": "closed"}) is False

    def test_complex_logical_expression(self):
        evaluator = ExpressionEvaluator()
        result = evaluator.evaluate(
            "(status == 'active' and priority > 5) or (status == 'pending' and urgent == True)",
            {"status": "pending", "priority": 3, "urgent": True}
        )
        assert result is True


class TestNestedConditions:
    """Test nested and complex expressions."""

    def test_multiple_levels(self):
        evaluator = ExpressionEvaluator()
        ctx = {
            "user": {"role": "admin", "active": True},
            "action": "delete"
        }
        # Test nested dict access via context
        assert evaluator.evaluate("user_active == True", {"user_active": True}) is True

    def test_chained_comparisons(self):
        evaluator = ExpressionEvaluator()
        # a < b < c style not directly supported but chained works differently
        result = evaluator.evaluate(
            "a >= 1 and a <= 10",
            {"a": 5}
        )
        assert result is True

    def test_mixed_operators(self):
        evaluator = ExpressionEvaluator()
        result = evaluator.evaluate(
            "status in ['active', 'pending'] and count > 0 and not disabled",
            {"status": "active", "count": 5, "disabled": False}
        )
        assert result is True


class TestMaliciousPayloads:
    """Test that malicious payloads are blocked."""

    def test_no_import_statement(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionEvaluationError):
            evaluator.evaluate("__import__('os').system('ls')", {})

    def test_no_eval_call(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("eval('1+1')", {})

    def test_no_exec_call(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("exec('print(1)')", {})

    def test_no_compile_call(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises((ExpressionSyntaxError, ExpressionEvaluationError)):
            evaluator.evaluate("compile('', '', 'exec')", {})

    def test_no_lambda(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("lambda: 1", {})

    def test_no_attribute_access(self):
        evaluator = ExpressionEvaluator()
        # Attribute access should be caught
        with pytest.raises((ExpressionSyntaxError, ExpressionEvaluationError)):
            evaluator.evaluate("().__class__", {})

    def test_no_open_call(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises((ExpressionSyntaxError, ExpressionEvaluationError)):
            evaluator.evaluate("open('/etc/passwd')", {})

    def test_no_method_calls(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises((ExpressionSyntaxError, ExpressionEvaluationError)):
            evaluator.evaluate("'test'.upper()", {})

    def test_no_subclasses(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises((ExpressionSyntaxError, ExpressionEvaluationError)):
            evaluator.evaluate("().__class__.__subclasses__()", {})

    def test_malicious_pattern_in_string(self):
        """Test that malicious patterns in string literals are allowed."""
        evaluator = ExpressionEvaluator()
        # String literals should be allowed even if they contain suspicious words
        result = evaluator.evaluate("message == '__import__'", {"message": "__import__"})
        assert result is True


class TestInvalidSyntax:
    """Test handling of invalid syntax."""

    def test_unbalanced_parens(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("(status == 'active'", {})

    def test_invalid_operator(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("status === 'active'", {})

    def test_unknown_variable(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionEvaluationError):
            evaluator.evaluate("unknown_var == 1", {})

    def test_empty_expression(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("", {})

    def test_malformed_list(self):
        evaluator = ExpressionEvaluator()
        with pytest.raises(ExpressionSyntaxError):
            evaluator.evaluate("status in [", {})


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_none_value(self):
        evaluator = ExpressionEvaluator()
        result = evaluator.evaluate("value == None", {"value": None})
        assert result is True

    def test_none_comparison(self):
        evaluator = ExpressionEvaluator()
        result = evaluator.evaluate("value is None", {"value": None})
        assert result is True

    def test_empty_string(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("msg == ''", {"msg": ""}) is True
        assert evaluator.evaluate("msg == ''", {"msg": "hello"}) is False

    def test_zero_value(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("count == 0", {"count": 0}) is True
        assert evaluator.evaluate("count > 0", {"count": 0}) is False

    def test_negative_numbers(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("temp < 0", {"temp": -10}) is True

    def test_float_comparison(self):
        evaluator = ExpressionEvaluator()
        assert evaluator.evaluate("price > 9.99", {"price": 15.50}) is True


class TestPerformance:
    """Test performance characteristics."""

    def test_simple_expression_speed(self):
        evaluator = ExpressionEvaluator()
        context = {"status": "active", "count": 10}

        start = time.perf_counter()
        for _ in range(1000):
            evaluator.evaluate("status == 'active' and count > 5", context)
        elapsed = time.perf_counter() - start

        # Should complete 1000 evaluations in under 1 second
        assert elapsed < 1.0, f"Took {elapsed}s for 1000 evaluations"

    def test_complex_expression_speed(self):
        evaluator = ExpressionEvaluator()
        context = {"a": 1, "b": 2, "c": 3, "d": 4, "e": 5}

        start = time.perf_counter()
        for _ in range(500):
            evaluator.evaluate(
                "a > 0 and b > 1 and c > 2 and d > 3 and e > 4",
                context
            )
        elapsed = time.perf_counter() - start

        assert elapsed < 1.0, f"Took {elapsed}s for 500 evaluations"

    def test_metrics_collection(self):
        """Test that metrics are collected correctly."""
        metrics = get_metrics()
        initial_total = metrics.total_evaluations

        evaluator = ExpressionEvaluator()
        evaluator.evaluate("status == 'active'", {"status": "active"})

        assert metrics.total_evaluations == initial_total + 1


class TestConvenienceFunction:
    """Test the convenience evaluate_expression function."""

    def test_simple_evaluation(self):
        result = evaluate_expression("status == 'open'", {"status": "open"})
        assert result is True

    def test_with_context(self):
        result = evaluate_expression(
            "priority > 3 and status != 'closed'",
            {"priority": 5, "status": "open"}
        )
        assert result is True


class TestValidation:
    """Test expression validation without evaluation."""

    def test_valid_expression_passes(self):
        assert parse_and_validate("status == 'active' and count > 5") is True

    def test_invalid_expression_fails(self):
        assert parse_and_validate("(status == 'active'") is False

    def test_malicious_expression_fails(self):
        assert parse_and_validate("__import__('os')") is False


class TestWorkflowIntegration:
    """Test expressions as used in workflow edge conditions."""

    def test_status_based_routing(self):
        """Simulate workflow edge condition evaluation."""
        evaluator = ExpressionEvaluator()

        # True path condition
        result = evaluator.evaluate(
            "message_type == 'inbound'",
            {"message_type": "inbound"}
        )
        assert result is True

        # False path condition
        result = evaluator.evaluate(
            "message_type == 'inbound'",
            {"message_type": "outbound"}
        )
        assert result is False

    def test_priority_based_routing(self):
        """Test priority-based workflow routing."""
        evaluator = ExpressionEvaluator()

        # High priority condition
        result = evaluator.evaluate(
            "priority >= 10",
            {"priority": 15}
        )
        assert result is True

        result = evaluator.evaluate(
            "priority >= 10",
            {"priority": 5}
        )
        assert result is False

    def test_time_based_condition(self):
        """Test time-based workflow conditions."""
        evaluator = ExpressionEvaluator()

        result = evaluator.evaluate(
            "hour >= 9 and hour < 17",
            {"hour": 14}
        )
        assert result is True

        result = evaluator.evaluate(
            "hour >= 9 and hour < 17",
            {"hour": 20}
        )
        assert result is False