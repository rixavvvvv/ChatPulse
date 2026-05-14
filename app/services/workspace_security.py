"""
Workspace Security Validation Module

Provides centralized workspace isolation and tenant boundary validation.
All service operations involving workspace-scoped resources must use these validators.

Key guarantees:
- Resource ownership validation
- Cross-workspace access prevention
- Tenant boundary enforcement
- Audit trail for access attempts
"""

import logging
from typing import Any, TypeVar

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

T = TypeVar('T')


class WorkspaceAccessDenied(Exception):
    """Raised when a resource access violates workspace boundaries."""

    def __init__(self, resource_type: str, resource_id: Any, requested_workspace: int, actual_workspace: int | None = None):
        self.resource_type = resource_type
        self.resource_id = resource_id
        self.requested_workspace = requested_workspace
        self.actual_workspace = actual_workspace
        super().__init__(
            f"Access denied: {resource_type} {resource_id} does not belong to workspace {requested_workspace}"
        )


class WorkspaceValidationError(Exception):
    """Raised when workspace validation itself fails."""
    pass


async def validate_workspace_ownership(
    db: AsyncSession,
    resource_model: Any,
    resource_id: int,
    expected_workspace_id: int,
    resource_name: str = "resource",
) -> dict:
    """
    Validate that a resource belongs to the expected workspace.

    Args:
        db: Database session
        resource_model: SQLAlchemy model class
        resource_id: ID of the resource to validate
        expected_workspace_id: Workspace ID that should own the resource
        resource_name: Name for logging/error messages

    Returns:
        Resource dict if valid

    Raises:
        WorkspaceAccessDenied: If resource belongs to different workspace
        WorkspaceValidationError: If resource not found
    """
    if expected_workspace_id <= 0:
        raise WorkspaceValidationError(f"Invalid workspace_id: {expected_workspace_id}")

    resource = await db.get(resource_model, resource_id)

    if resource is None:
        raise WorkspaceValidationError(f"{resource_name} {resource_id} not found")

    # Check workspace_id attribute exists
    if not hasattr(resource, 'workspace_id'):
        raise WorkspaceValidationError(f"{resource_name} {resource_id} has no workspace_id attribute")

    actual_workspace = resource.workspace_id

    if actual_workspace != expected_workspace_id:
        logger.warning(
            "Workspace isolation violation: %s %d owned by workspace %d, access attempted by workspace %d",
            resource_name,
            resource_id,
            actual_workspace,
            expected_workspace_id,
        )
        raise WorkspaceAccessDenied(
            resource_type=resource_name,
            resource_id=resource_id,
            requested_workspace=expected_workspace_id,
            actual_workspace=actual_workspace,
        )

    return resource


async def validate_trigger_ownership(
    db: AsyncSession,
    trigger_id: int,
    workspace_id: int,
) -> dict:
    """
    Validate that a workflow trigger belongs to the specified workspace.

    Args:
        db: Database session
        trigger_id: Trigger ID to validate
        workspace_id: Expected workspace ID

    Returns:
        Trigger dict if valid

    Raises:
        WorkspaceAccessDenied: If trigger belongs to different workspace
    """
    from app.models.workflow_trigger import WorkflowTrigger
    return await validate_workspace_ownership(
        db,
        WorkflowTrigger,
        trigger_id,
        workspace_id,
        "trigger",
    )


async def validate_workflow_ownership(
    db: AsyncSession,
    workflow_definition_id: int,
    workspace_id: int,
) -> dict:
    """
    Validate that a workflow definition belongs to the specified workspace.

    Args:
        db: Database session
        workflow_definition_id: Workflow definition ID to validate
        workspace_id: Expected workspace ID

    Returns:
        Workflow definition dict if valid

    Raises:
        WorkspaceAccessDenied: If workflow belongs to different workspace
    """
    from app.models.workflow import WorkflowDefinition
    return await validate_workspace_ownership(
        db,
        WorkflowDefinition,
        workflow_definition_id,
        workspace_id,
        "workflow",
    )


async def validate_delayed_execution_ownership(
    db: AsyncSession,
    execution_id: int,
    workspace_id: int,
) -> dict:
    """
    Validate that a delayed execution belongs to the specified workspace.

    Args:
        db: Database session
        execution_id: Delayed execution ID to validate
        workspace_id: Expected workspace ID

    Returns:
        Delayed execution dict if valid

    Raises:
        WorkspaceAccessDenied: If execution belongs to different workspace
    """
    from app.models.workflow_delayed import DelayedExecution
    return await validate_workspace_ownership(
        db,
        DelayedExecution,
        execution_id,
        workspace_id,
        "delayed_execution",
    )


async def validate_conversation_ownership(
    db: AsyncSession,
    conversation_id: int,
    workspace_id: int,
) -> dict:
    """
    Validate that a conversation belongs to the specified workspace.

    Args:
        db: Database session
        conversation_id: Conversation ID to validate
        workspace_id: Expected workspace ID

    Returns:
        Conversation dict if valid

    Raises:
        WorkspaceAccessDenied: If conversation belongs to different workspace
    """
    from app.models.conversation import Conversation
    return await validate_workspace_ownership(
        db,
        Conversation,
        conversation_id,
        workspace_id,
        "conversation",
    )


async def validate_campaign_ownership(
    db: AsyncSession,
    campaign_id: int,
    workspace_id: int,
) -> dict:
    """
    Validate that a campaign belongs to the specified workspace.

    Args:
        db: Database session
        campaign_id: Campaign ID to validate
        workspace_id: Expected workspace ID

    Returns:
        Campaign dict if valid

    Raises:
        WorkspaceAccessDenied: If campaign belongs to different workspace
    """
    from app.models.campaign import Campaign
    return await validate_workspace_ownership(
        db,
        Campaign,
        campaign_id,
        workspace_id,
        "campaign",
    )


async def validate_automation_ownership(
    db: AsyncSession,
    automation_id: int,
    workspace_id: int,
) -> dict:
    """
    Validate that an ecommerce automation belongs to the specified workspace.

    Args:
        db: Database session
        automation_id: Automation ID to validate
        workspace_id: Expected workspace ID

    Returns:
        Automation dict if valid

    Raises:
        WorkspaceAccessDenied: If automation belongs to different workspace
    """
    from app.models.ecommerce_automation import EcommerceAutomation
    return await validate_workspace_ownership(
        db,
        EcommerceAutomation,
        automation_id,
        workspace_id,
        "automation",
    )


async def require_workspace_id(workspace_id: int, operation: str = "operation") -> None:
    """
    Validate that workspace_id is valid (positive integer).

    Args:
        workspace_id: Workspace ID to validate
        operation: Operation name for error message

    Raises:
        WorkspaceValidationError: If workspace_id is invalid
    """
    if workspace_id is None:
        raise WorkspaceValidationError(f"{operation} requires workspace_id, got None")
    if not isinstance(workspace_id, int):
        raise WorkspaceValidationError(f"{operation} requires integer workspace_id, got {type(workspace_id)}")
    if workspace_id <= 0:
        raise WorkspaceValidationError(f"{operation} requires valid workspace_id > 0, got {workspace_id}")


def get_workspace_safe_query(
    base_query: Any,
    workspace_id: int,
    resource_column: Any,
) -> Any:
    """
    Modify a query to always include workspace_id filter.

    Use this to ensure all queries are workspace-scoped.

    Args:
        base_query: Base SQLAlchemy query
        workspace_id: Workspace ID to filter by
        resource_column: Column representing workspace_id

    Returns:
        Modified query with workspace filter
    """
    return base_query.where(resource_column == workspace_id)


class WorkspaceContext:
    """
    Context manager for workspace-scoped operations.

    Ensures all database operations within the context are scoped to a workspace.

    Usage:
        async with WorkspaceContext(db, workspace_id) as ctx:
            trigger = await ctx.validate_and_get_trigger(trigger_id)
    """

    def __init__(self, db: AsyncSession, workspace_id: int):
        self.db = db
        self.workspace_id = workspace_id

    async def __aenter__(self):
        await require_workspace_id(self.workspace_id, "WorkspaceContext")
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        return False

    async def validate_trigger(self, trigger_id: int) -> dict:
        """Validate and return trigger."""
        return await validate_trigger_ownership(self.db, trigger_id, self.workspace_id)

    async def validate_workflow(self, workflow_id: int) -> dict:
        """Validate and return workflow."""
        return await validate_workflow_ownership(self.db, workflow_id, self.workspace_id)

    async def validate_delayed_execution(self, execution_id: int) -> dict:
        """Validate and return delayed execution."""
        return await validate_delayed_execution_ownership(self.db, execution_id, self.workspace_id)

    async def validate_conversation(self, conversation_id: int) -> dict:
        """Validate and return conversation."""
        return await validate_conversation_ownership(self.db, conversation_id, self.workspace_id)

    async def validate_campaign(self, campaign_id: int) -> dict:
        """Validate and return campaign."""
        return await validate_campaign_ownership(self.db, campaign_id, self.workspace_id)

    async def validate_automation(self, automation_id: int) -> dict:
        """Validate and return automation."""
        return await validate_automation_ownership(self.db, automation_id, self.workspace_id)