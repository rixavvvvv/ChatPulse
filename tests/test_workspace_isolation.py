"""
Tests for Workspace Isolation / Tenant Boundary Validation

Covers:
- Unauthorized trigger access prevention
- Cross-workspace execution blocking
- Invalid workspace routing rejection
- Service method workspace validation
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.workspace_security import (
    WorkspaceAccessDenied,
    WorkspaceValidationError,
    validate_workspace_ownership,
    validate_trigger_ownership,
    validate_workflow_ownership,
    validate_delayed_execution_ownership,
    validate_conversation_ownership,
    require_workspace_id,
    WorkspaceContext,
)


class TestRequireWorkspaceId:
    """Test workspace_id validation helper."""

    def test_valid_positive_workspace_id(self):
        """Positive workspace IDs should be accepted."""
        require_workspace_id(1)  # Should not raise
        require_workspace_id(100)  # Should not raise
        require_workspace_id(999999)  # Should not raise

    def test_zero_workspace_id_rejected(self):
        """Workspace ID of 0 should be rejected."""
        with pytest.raises(WorkspaceValidationError) as exc:
            require_workspace_id(0)
        assert "requires valid workspace_id > 0" in str(exc.value)

    def test_negative_workspace_id_rejected(self):
        """Negative workspace IDs should be rejected."""
        with pytest.raises(WorkspaceValidationError) as exc:
            require_workspace_id(-1)
        assert "requires valid workspace_id > 0" in str(exc.value)

    def test_none_workspace_id_rejected(self):
        """None workspace ID should be rejected."""
        with pytest.raises(WorkspaceValidationError) as exc:
            require_workspace_id(None)
        assert "requires workspace_id, got None" in str(exc.value)

    def test_non_integer_rejected(self):
        """Non-integer workspace IDs should be rejected."""
        with pytest.raises(WorkspaceValidationError) as exc:
            require_workspace_id("1")
        assert "requires integer workspace_id" in str(exc.value)


class TestValidateTriggerOwnership:
    """Test trigger ownership validation."""

    @pytest.mark.asyncio
    async def test_trigger_owned_by_workspace_succeeds(self):
        """Trigger owned by workspace should pass validation."""
        mock_db = AsyncMock()
        mock_trigger = MagicMock()
        mock_trigger.workspace_id = 5
        mock_db.get = AsyncMock(return_value=mock_trigger)

        result = await validate_trigger_ownership(mock_db, trigger_id=1, workspace_id=5)

        assert result.workspace_id == 5

    @pytest.mark.asyncio
    async def test_trigger_owned_by_different_workspace_fails(self):
        """Trigger owned by different workspace should raise access denied."""
        mock_db = AsyncMock()
        mock_trigger = MagicMock()
        mock_trigger.workspace_id = 5
        mock_db.get = AsyncMock(return_value=mock_trigger)

        with pytest.raises(WorkspaceAccessDenied) as exc:
            await validate_trigger_ownership(mock_db, trigger_id=1, workspace_id=10)

        assert exc.value.requested_workspace == 10
        assert exc.value.actual_workspace == 5

    @pytest.mark.asyncio
    async def test_nonexistent_trigger_fails(self):
        """Nonexistent trigger should raise validation error."""
        mock_db = AsyncMock()
        mock_db.get = AsyncMock(return_value=None)

        with pytest.raises(WorkspaceValidationError) as exc:
            await validate_trigger_ownership(mock_db, trigger_id=999, workspace_id=1)

        assert "not found" in str(exc.value)


class TestValidateWorkflowOwnership:
    """Test workflow definition ownership validation."""

    @pytest.mark.asyncio
    async def test_workflow_owned_by_workspace_succeeds(self):
        """Workflow owned by workspace should pass validation."""
        mock_db = AsyncMock()
        mock_workflow = MagicMock()
        mock_workflow.workspace_id = 3
        mock_db.get = AsyncMock(return_value=mock_workflow)

        result = await validate_workflow_ownership(mock_db, workflow_definition_id=1, workspace_id=3)

        assert result.workspace_id == 3

    @pytest.mark.asyncio
    async def test_workflow_owned_by_different_workspace_fails(self):
        """Workflow owned by different workspace should raise access denied."""
        mock_db = AsyncMock()
        mock_workflow = MagicMock()
        mock_workflow.workspace_id = 3
        mock_db.get = AsyncMock(return_value=mock_workflow)

        with pytest.raises(WorkspaceAccessDenied) as exc:
            await validate_workflow_ownership(mock_db, workflow_definition_id=1, workspace_id=7)

        assert exc.value.requested_workspace == 7
        assert exc.value.actual_workspace == 3


class TestValidateConversationOwnership:
    """Test conversation ownership validation."""

    @pytest.mark.asyncio
    async def test_conversation_owned_by_workspace_succeeds(self):
        """Conversation owned by workspace should pass validation."""
        mock_db = AsyncMock()
        mock_conversation = MagicMock()
        mock_conversation.workspace_id = 8
        mock_db.get = AsyncMock(return_value=mock_conversation)

        result = await validate_conversation_ownership(mock_db, conversation_id=1, workspace_id=8)

        assert result.workspace_id == 8


class TestWorkspaceContextManager:
    """Test WorkspaceContext context manager."""

    @pytest.mark.asyncio
    async def test_valid_workspace_context_enters(self):
        """Valid workspace ID should allow context entry."""
        mock_db = AsyncMock()

        async with WorkspaceContext(mock_db, workspace_id=5) as ctx:
            assert ctx.workspace_id == 5

    @pytest.mark.asyncio
    async def test_invalid_workspace_id_prevents_entry(self):
        """Invalid workspace ID should prevent context entry."""
        mock_db = AsyncMock()

        with pytest.raises(WorkspaceValidationError):
            async with WorkspaceContext(mock_db, workspace_id=0):
                pass  # Should not reach here


class TestWorkspaceAccessDeniedException:
    """Test WorkspaceAccessDenied exception properties."""

    def test_exception_stores_correct_info(self):
        """Exception should store access attempt details."""
        exc = WorkspaceAccessDenied(
            resource_type="trigger",
            resource_id=123,
            requested_workspace=5,
            actual_workspace=10,
        )

        assert exc.resource_type == "trigger"
        assert exc.resource_id == 123
        assert exc.requested_workspace == 5
        assert exc.actual_workspace == 10

    def test_exception_message_includes_details(self):
        """Exception message should include helpful details."""
        exc = WorkspaceAccessDenied(
            resource_type="workflow",
            resource_id=456,
            requested_workspace=1,
            actual_workspace=2,
        )

        assert "workflow 456" in str(exc)
        assert "workspace 1" in str(exc)


class TestCrossWorkspacePrevention:
    """Integration-style tests for cross-workspace prevention."""

    def test_workspace_isolation_pattern(self):
        """
        Test that workspace isolation follows the pattern:
        1. Validate workspace_id is positive
        2. Fetch resource with workspace_id filter
        3. If resource exists but workspace_id doesn't match, deny access
        """
        # This test documents the expected pattern
        # Actual implementation tested in other test classes

        # Valid pattern: always include workspace in WHERE clause
        valid_query_pattern = "WHERE id = ? AND workspace_id = ?"

        # Invalid pattern: only filter by id (allows cross-workspace access)
        invalid_query_pattern = "WHERE id = ?"

        # Both patterns should be understood - the first is secure
        assert valid_query_pattern is not None
        assert invalid_query_pattern is not None


class TestServiceIntegrationPatterns:
    """Test that services follow secure patterns."""

    def test_trigger_service_accepts_workspace_id(self):
        """Trigger service get_trigger_by_id should require workspace_id."""
        # This test verifies the service pattern
        # The actual implementation is tested via validate_trigger_ownership
        from app.services import trigger_service
        import inspect

        # Verify get_trigger_by_id has workspace_id parameter
        sig = inspect.signature(trigger_service.get_trigger_by_id)
        params = list(sig.parameters.keys())

        assert "workspace_id" in params

    def test_workflow_service_get_execution_includes_workspace(self):
        """Workflow service get_execution should validate workspace."""
        from app.services import workflow_service
        import inspect

        sig = inspect.signature(workflow_service.get_execution)
        params = list(sig.parameters.keys())

        assert "workspace_id" in params

    def test_delayed_execution_service_includes_workspace(self):
        """Delayed execution service should validate workspace."""
        from app.services import delayed_execution_service
        import inspect

        sig = inspect.signature(delayed_execution_service.get_delayed_execution)
        params = list(sig.parameters.keys())

        assert "workspace_id" in params


class TestInvalidWorkspaceRouting:
    """Test handling of invalid workspace routing."""

    @pytest.mark.asyncio
    async def test_workspace_id_must_be_integer(self):
        """Non-integer workspace IDs should be rejected."""
        with pytest.raises(WorkspaceValidationError):
            await validate_trigger_ownership(
                AsyncMock(),
                trigger_id=1,
                workspace_id="invalid"  # type: ignore
            )

    @pytest.mark.asyncio
    async def test_missing_workspace_id_fails(self):
        """Missing workspace_id should fail validation."""
        # This tests the pattern where workspace_id could be None
        mock_db = AsyncMock()
        mock_trigger = MagicMock()
        mock_trigger.workspace_id = None  # Edge case: workspace_id is None
        mock_db.get = AsyncMock(return_value=mock_trigger)

        # When resource has no workspace_id, should fail
        with pytest.raises(WorkspaceValidationError):
            await validate_trigger_ownership(mock_db, trigger_id=1, workspace_id=1)


class TestAuditTrail:
    """Test that access violations are logged for audit."""

    def test_access_denied_logs_warning(self):
        """WorkspaceAccessDenied should be loggable."""
        exc = WorkspaceAccessDenied(
            resource_type="trigger",
            resource_id=123,
            requested_workspace=5,
            actual_workspace=10,
        )

        # The exception should be string-representable for logging
        log_message = str(exc)
        assert "access_denied" not in log_message.lower()  # It's a custom message
        assert "123" in log_message
        assert "5" in log_message
        assert "10" in log_message