"""
Tests for structured logging infrastructure.

Tests cover:
- Log schema and JSON formatting
- PII redaction
- Context variable propagation
- Logger usage
- Timed operations
"""

import json
import time
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from app.logging import (
    LogLevel,
    LogSchema,
    PIIRedactor,
    get_logger,
    get_request_id,
    get_task_id,
    get_trace_id,
    get_workspace_id,
    log_context,
    set_request_id,
    set_task_id,
    set_trace_id,
    set_workspace_id,
    setup_logging,
)


# ─────────────────────────────────────────────────────────────────────────────
# LogSchema Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLogSchema:
    """Test LogSchema dataclass."""

    def test_schema_creation(self):
        """Should create schema with required fields."""
        schema = LogSchema(
            level="INFO",
            event="test.event",
            message="Test message",
        )

        assert schema.level == "INFO"
        assert schema.event == "test.event"
        assert schema.message == "Test message"
        assert schema.service == "chatpulse"
        assert schema.timestamp is not None

    def test_schema_to_dict(self):
        """Should convert schema to dictionary."""
        schema = LogSchema(
            level="INFO",
            event="campaign.send",
            message="Campaign sent",
            trace_id="trace-123",
            workspace_id=456,
            duration_ms=1500.5,
        )

        data = schema.to_dict()

        assert data["level"] == "INFO"
        assert data["event"] == "campaign.send"
        assert data["trace_id"] == "trace-123"
        assert data["workspace_id"] == 456
        assert data["duration_ms"] == 1500.5
        # Service should be present
        assert data["service"] == "chatpulse"

    def test_schema_to_dict_excludes_empty(self):
        """Should exclude optional fields when empty."""
        schema = LogSchema(
            level="INFO",
            event="test",
            message="Test",
        )

        data = schema.to_dict()

        assert "trace_id" not in data
        assert "workspace_id" not in data
        assert "task_id" not in data
        assert "duration_ms" not in data

    def test_schema_to_json(self):
        """Should convert schema to JSON string."""
        schema = LogSchema(
            level="INFO",
            event="test",
            message="Test",
        )

        json_str = schema.to_json()
        data = json.loads(json_str)

        assert data["event"] == "test"
        assert data["level"] == "INFO"

    def test_schema_metadata_redaction(self):
        """Should redact PII from metadata."""
        schema = LogSchema(
            level="INFO",
            event="test",
            message="Test",
            metadata={
                "email": "user@example.com",
                "password": "secret123",
            },
        )

        data = schema.to_dict()

        assert data["metadata"]["email"] == "[EMAIL]"
        assert data["metadata"]["password"] == "[REDACTED]"


# ─────────────────────────────────────────────────────────────────────────────
# PII Redaction Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestPIIRedaction:
    """Test PII redaction functionality."""

    def test_redact_email(self):
        """Should redact email addresses."""
        text = "Contact user at john@example.com for details"
        result = PIIRedactor.redact(text)

        assert "john@example.com" not in result
        assert "[EMAIL]" in result

    def test_redact_phone_numbers(self):
        """Should redact phone numbers when enabled."""
        text = "Call +1-234-567-8900 or 2345678901"
        result = PIIRedactor.redact(text, redact_phone=True)

        assert "+1-234-567-8900" not in result
        assert "2345678901" not in result
        assert "[PHONE]" in result

    def test_redact_phone_disabled(self):
        """Should NOT redact phone numbers when disabled."""
        text = "Call +1-234-567-8900"
        result = PIIRedactor.redact(text, redact_phone=False)

        assert "+1-234-567-8900" in result

    def test_redact_api_key(self):
        """Should redact API keys."""
        text = "api_key=sk-1234567890abcdef"
        result = PIIRedactor.redact(text)

        assert "sk-1234567890abcdef" not in result
        assert "[REDACTED_KEY]" in result

    def test_redact_bearer_token(self):
        """Should redact bearer tokens."""
        text = "Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        result = PIIRedactor.redact(text)

        assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in result
        assert "Bearer [REDACTED_TOKEN]" in result

    def test_redact_credit_card(self):
        """Should redact credit card numbers."""
        text = "Card: 4111-1111-1111-1111"
        result = PIIRedactor.redact(text)

        assert "4111-1111-1111-1111" not in result
        assert "[CARD]" in result

    def test_redact_dict(self):
        """Should redact sensitive fields in dictionary."""
        data = {
            "email": "test@example.com",
            "password": "secret",
            "name": "John",
            "api_key": "key-123",
        }

        result = PIIRedactor.redact_dict(data)

        assert result["email"] == "[EMAIL]"
        assert result["password"] == "[REDACTED]"
        assert result["api_key"] == "[REDACTED]"
        assert result["name"] == "John"

    def test_redact_dict_nested(self):
        """Should redact nested dictionaries."""
        data = {
            "user": {
                "email": "test@example.com",
                "credentials": {
                    "password": "secret",
                },
            },
        }

        result = PIIRedactor.redact_dict(data)

        assert result["user"]["email"] == "[EMAIL]"
        assert result["user"]["credentials"]["password"] == "[REDACTED]"

    def test_redact_dict_list(self):
        """Should redact items in lists."""
        data = {
            "users": [
                {"email": "a@example.com"},
                {"email": "b@example.com"},
            ],
        }

        result = PIIRedactor.redact_dict(data)

        assert result["users"][0]["email"] == "[EMAIL]"
        assert result["users"][1]["email"] == "[EMAIL]"

    def test_redact_none(self):
        """Should handle None values."""
        result = PIIRedactor.redact_dict(None)
        assert result is None

    def test_redact_non_string(self):
        """Should handle non-string values."""
        result = PIIRedactor.redact(123)
        assert result == 123


# ─────────────────────────────────────────────────────────────────────────────
# Context Variable Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestContextVariables:
    """Test context variable get/set functions."""

    def test_trace_id_generation(self):
        """Should generate trace_id when not set."""
        trace_id = set_trace_id()
        assert trace_id is not None
        assert len(trace_id) == 12

    def test_trace_id_custom(self):
        """Should use custom trace_id."""
        trace_id = set_trace_id("custom-trace-id")
        assert get_trace_id() == "custom-trace-id"

    def test_workspace_id(self):
        """Should set and get workspace_id."""
        set_workspace_id(123)
        assert get_workspace_id() == 123

        set_workspace_id(None)
        assert get_workspace_id() is None

    def test_task_id(self):
        """Should set and get task_id."""
        set_task_id("task-123")
        assert get_task_id() == "task-123"

    def test_request_id(self):
        """Should set and get request_id."""
        set_request_id("req-456")
        assert get_request_id() == "req-456"

    def test_context_manager(self):
        """Should restore context after context manager."""
        set_workspace_id(100)

        with log_context(workspace_id=200):
            assert get_workspace_id() == 200
            # Trace ID also set
            assert get_trace_id() != ""

        # Context restored
        assert get_workspace_id() == 100

    def test_context_manager_restores_on_exception(self):
        """Should restore context even on exception."""
        set_workspace_id(100)

        with pytest.raises(ValueError):
            with log_context(workspace_id=200):
                raise ValueError("Test")

        assert get_workspace_id() == 100

    def test_context_manager_multiple_vars(self):
        """Should handle multiple context variables."""
        with log_context(
            trace_id="trace-abc",
            workspace_id=300,
            task_id="task-xyz",
        ):
            assert get_trace_id() == "trace-abc"
            assert get_workspace_id() == 300
            assert get_task_id() == "task-xyz"


# ─────────────────────────────────────────────────────────────────────────────
# Logger Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestChatPulseLogger:
    """Test ChatPulseLogger wrapper."""

    def test_get_logger_singleton(self):
        """Should return same logger for same name."""
        logger1 = get_logger("test.module")
        logger2 = get_logger("test.module")

        assert logger1 is logger2

    def test_logger_has_info_method(self):
        """Logger should have info method."""
        logger = get_logger(__name__)
        assert hasattr(logger, "info")

    def test_logger_has_warning_method(self):
        """Logger should have warning method."""
        logger = get_logger(__name__)
        assert hasattr(logger, "warning")

    def test_logger_has_error_method(self):
        """Logger should have error method."""
        logger = get_logger(__name__)
        assert hasattr(logger, "error")

    def test_logger_has_critical_method(self):
        """Logger should have critical method."""
        logger = get_logger(__name__)
        assert hasattr(logger, "critical")

    def test_logger_has_audit_method(self):
        """Logger should have audit method."""
        logger = get_logger(__name__)
        assert hasattr(logger, "audit")

    def test_logger_has_timed_context_manager(self):
        """Logger should have timed context manager."""
        logger = get_logger(__name__)
        assert hasattr(logger, "timed")


class TestLoggerTimed:
    """Test timed context manager."""

    def test_timed_on_success(self):
        """Should log duration on success."""
        logger = get_logger(__name__)

        with patch.object(logger, 'info') as mock_info:
            with logger.timed("test.operation"):
                time.sleep(0.01)  # 10ms

            mock_info.assert_called_once()
            call_args = mock_info.call_args
            # Should have duration_ms in kwargs
            assert "duration_ms" in call_args.kwargs

    def test_timed_on_failure(self):
        """Should log error on exception."""
        logger = get_logger(__name__)

        with patch.object(logger, 'error') as mock_error:
            with pytest.raises(ValueError):
                with logger.timed("test.operation"):
                    raise ValueError("Test error")

            mock_error.assert_called_once()


# ─────────────────────────────────────────────────────────────────────────────
# Setup Logging Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestSetupLogging:
    """Test logging setup function."""

    def test_setup_logging_no_exception(self):
        """Should set up logging without exception."""
        # This should not raise
        setup_logging(level="DEBUG", json_format=True)

    def test_setup_logging_json_format(self):
        """Should configure JSON format."""
        setup_logging(level="INFO", json_format=True)

        # Verify handlers are configured
        import logging
        root = logging.getLogger()
        assert len(root.handlers) > 0


# ─────────────────────────────────────────────────────────────────────────────
# LogLevel Enum Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLogLevel:
    """Test LogLevel enum."""

    def test_log_levels_exist(self):
        """All standard log levels should exist."""
        assert LogLevel.DEBUG.value == "DEBUG"
        assert LogLevel.INFO.value == "INFO"
        assert LogLevel.WARNING.value == "WARNING"
        assert LogLevel.ERROR.value == "ERROR"
        assert LogLevel.CRITICAL.value == "CRITICAL"

    def test_log_level_string_comparison(self):
        """Log levels should be comparable as strings."""
        assert LogLevel.INFO == "INFO"
        assert str(LogLevel.INFO) == "INFO"


# ─────────────────────────────────────────────────────────────────────────────
# Integration Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLoggingIntegration:
    """Integration tests for logging system."""

    def test_full_context_propagation(self):
        """Should propagate context through nested calls."""
        trace_id = set_trace_id("integration-trace")
        set_workspace_id(123)
        set_task_id("task-integration")
        set_request_id("req-integration")

        # Simulate a logged operation
        schema = LogSchema(
            level="INFO",
            event="integration.test",
            message="Test message",
        )
        data = schema.to_dict()

        assert data["trace_id"] == "integration-trace"
        assert data["workspace_id"] == 123
        assert data["task_id"] == "task-integration"

    def test_pii_in_metadata(self):
        """Should redact PII in metadata."""
        schema = LogSchema(
            level="INFO",
            event="user.action",
            message="User action",
            metadata={
                "user_email": "sensitive@example.com",
                "action": "login",
            },
        )

        data = schema.to_dict()
        assert "[EMAIL]" in data["metadata"]["user_email"]
        assert data["metadata"]["action"] == "login"

    def test_event_naming_convention(self):
        """Should follow event naming convention."""
        events = [
            "campaign.send.started",
            "campaign.send.completed",
            "webhook.received",
            "webhook.processed",
            "message.sent",
        ]

        for event in events:
            schema = LogSchema(
                level="INFO",
                event=event,
                message="Test",
            )
            data = schema.to_dict()
            assert data["event"] == event

    def test_duration_formatting(self):
        """Should handle duration_ms correctly."""
        schema = LogSchema(
            level="INFO",
            event="test",
            message="Test",
            duration_ms=1234.567,
        )

        data = schema.to_dict()
        assert data["duration_ms"] == 1234.567


# ─────────────────────────────────────────────────────────────────────────────
# Performance Tests
# ─────────────────────────────────────────────────────────────────────────────

class TestLoggingPerformance:
    """Performance tests for logging infrastructure."""

    def test_schema_creation_performance(self):
        """Schema creation should be fast."""
        import time

        start = time.perf_counter()
        for _ in range(1000):
            LogSchema(level="INFO", event="test", message="Test")
        duration = time.perf_counter() - start

        # Should be able to create 1000 schemas in under 100ms
        assert duration < 0.1

    def test_redaction_performance(self):
        """Redaction should be fast."""
        import time

        text = "Contact user@example.com at +1234567890 with api_key=secret123"

        start = time.perf_counter()
        for _ in range(1000):
            PIIRedactor.redact(text, redact_phone=True)
        duration = time.perf_counter() - start

        # Should be able to redact 1000 strings in under 100ms
        assert duration < 0.1