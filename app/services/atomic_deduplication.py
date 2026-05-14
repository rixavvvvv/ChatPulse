"""
Atomic Deduplication Service

Provides atomic insert-or-get semantics for duplicate prevention across all execution types.
Uses PostgreSQL unique constraints and INSERT ... ON CONFLICT for race-condition-safe deduplication.

Supported patterns:
1. Idempotency key based (per operation)
2. Composite key based (e.g., automation_id + order_id)
3. Execution ID based (eager validation)
"""

import hashlib
import logging
from datetime import datetime
from typing import Any

from sqlalchemy import and_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class DuplicateExecutionError(Exception):
    """
    Raised when attempting to create a duplicate execution.

    Contains the existing execution for caller to use instead of creating new.
    """

    def __init__(self, message: str, existing_execution_id: int | None = None, existing_status: str | None = None):
        super().__init__(message)
        self.existing_execution_id = existing_execution_id
        self.existing_status = existing_status


class AtomicDeduplicationService:
    """
    Provides atomic operations for duplicate prevention.

    Uses PostgreSQL's INSERT ... ON CONFLICT (upsert) for true atomicity.
    """

    def __init__(self, db: AsyncSession):
        self.db = db

    async def create_if_not_exists_trigger_execution(
        self,
        workspace_id: int,
        workflow_trigger_id: int,
        event_id: int,
        dedupe_key: str,
        event_payload: dict[str, Any],
    ) -> tuple[int, bool]:
        """
        Atomically create a trigger execution if one with the same dedupe_key doesn't exist.

        Args:
            workspace_id: Workspace ID
            workflow_trigger_id: Trigger ID
            event_id: Event ID
            dedupe_key: Idempotency key
            event_payload: Event data

        Returns:
            Tuple of (execution_id, created) where created=True if new execution was created
        """
        from app.models.workflow_trigger import TriggerExecution, TriggerExecutionStatus

        # Use raw INSERT ... ON CONFLICT for atomicity
        stmt = insert(TriggerExecution).values(
            workspace_id=workspace_id,
            workflow_trigger_id=workflow_trigger_id,
            event_id=event_id,
            dedupe_key=dedupe_key,
            status=TriggerExecutionStatus.pending,
            event_payload=event_payload,
        ).on_conflict_do_nothing(
            index_elements=["workflow_trigger_id", "dedupe_key"]
        ).returning(TriggerExecution.id)

        result = await self.db.execute(stmt)
        new_id = result.scalar_one_or_none()

        if new_id is not None:
            return new_id, True

        # Conflict occurred - fetch existing execution
        existing = await self.db.execute(
            select(TriggerExecution).where(
                and_(
                    TriggerExecution.workflow_trigger_id == workflow_trigger_id,
                    TriggerExecution.dedupe_key == dedupe_key,
                )
            )
        )
        existing_exec = existing.scalar_one_or_none()
        if existing_exec:
            return existing_exec.id, False

        # Edge case: concurrent insert succeeded, return failure
        raise DuplicateExecutionError(
            "Failed to create trigger execution",
            existing_execution_id=None
        )

    async def create_if_not_exists_delayed_execution(
        self,
        workspace_id: int,
        workflow_definition_id: int,
        execution_id: str,
        delay_type: str,
        delay_config: dict[str, Any],
        scheduled_at: datetime,
        context: dict[str, Any],
        trigger_data: dict[str, Any],
        idempotency_key: str,
        max_retries: int = 3,
    ) -> tuple[int, bool]:
        """
        Atomically create a delayed execution if one with the same idempotency_key doesn't exist.

        Args:
            workspace_id: Workspace ID
            workflow_definition_id: Workflow definition ID
            execution_id: Unique execution ID string
            delay_type: Type of delay
            delay_config: Delay configuration
            scheduled_at: When to execute
            context: Execution context
            trigger_data: Trigger event data
            idempotency_key: Idempotency key for deduplication
            max_retries: Maximum retry attempts

        Returns:
            Tuple of (execution_id, created) where created=True if new execution was created
        """
        from app.models.workflow_delayed import DelayedExecution, DelayedExecutionStatus

        stmt = insert(DelayedExecution).values(
            workspace_id=workspace_id,
            workflow_definition_id=workflow_definition_id,
            execution_id=execution_id,
            delay_type=delay_type,
            delay_config=delay_config,
            scheduled_at=scheduled_at,
            status=DelayedExecutionStatus.scheduled,
            context=context,
            trigger_data=trigger_data,
            idempotency_key=idempotency_key,
            max_retries=max_retries,
        ).on_conflict_do_nothing(
            index_elements=["idempotency_key"]
        ).returning(DelayedExecution.id)

        result = await self.db.execute(stmt)
        new_id = result.scalar_one_or_none()

        if new_id is not None:
            return new_id, True

        # Conflict occurred - fetch existing execution
        existing = await self.db.execute(
            select(DelayedExecution).where(
                DelayedExecution.idempotency_key == idempotency_key
            )
        )
        existing_exec = existing.scalar_one_or_none()
        if existing_exec:
            return existing_exec.id, False

        raise DuplicateExecutionError("Failed to create delayed execution")

    async def create_if_not_exists_ecommerce_execution(
        self,
        workspace_id: int,
        automation_id: int,
        execution_id: str,
        order_id: str | None,
        cart_id: str | None,
        contact_id: int | None,
        trigger_data: dict[str, Any],
        idempotency_key: str | None = None,
    ) -> tuple[int, bool]:
        """
        Atomically create an ecommerce execution if one with the same idempotency_key doesn't exist.

        Args:
            workspace_id: Workspace ID
            automation_id: Automation ID
            execution_id: Unique execution ID string
            order_id: Order ID (optional)
            cart_id: Cart ID (optional)
            contact_id: Contact ID
            trigger_data: Trigger event data
            idempotency_key: Idempotency key for deduplication

        Returns:
            Tuple of (execution_id, created) where created=True if new execution was created
        """
        from app.models.ecommerce_automation import EcommerceAutomationExecution, ExecutionStatus

        values = dict(
            workspace_id=workspace_id,
            automation_id=automation_id,
            execution_id=execution_id,
            order_id=order_id,
            cart_id=cart_id,
            contact_id=contact_id,
            status=ExecutionStatus.pending,
            trigger_data=trigger_data,
            message_payload={},
        )

        if idempotency_key:
            values["idempotency_key"] = idempotency_key

        # Use idempotency_key if provided, otherwise use execution_id
        if idempotency_key:
            index_elements = ["automation_id", "idempotency_key"]
        else:
            index_elements = ["execution_id"]

        stmt = insert(EcommerceAutomationExecution).values(**values).on_conflict_do_nothing(
            index_elements=index_elements
        ).returning(EcommerceAutomationExecution.id)

        result = await self.db.execute(stmt)
        new_id = result.scalar_one_or_none()

        if new_id is not None:
            return new_id, True

        # Conflict occurred - fetch existing execution
        if idempotency_key:
            existing = await self.db.execute(
                select(EcommerceAutomationExecution).where(
                    and_(
                        EcommerceAutomationExecution.automation_id == automation_id,
                        EcommerceAutomationExecution.idempotency_key == idempotency_key,
                    )
                )
            )
        else:
            existing = await self.db.execute(
                select(EcommerceAutomationExecution).where(
                    EcommerceAutomationExecution.execution_id == execution_id
                )
            )

        existing_exec = existing.scalar_one_or_none()
        if existing_exec:
            return existing_exec.id, False

        raise DuplicateExecutionError("Failed to create ecommerce execution")

    async def get_or_create_with_lease(
        self,
        execution_id: int,
        worker_id: str,
        lease_duration_seconds: int = 300,
    ) -> bool:
        """
        Atomically acquire a lease on an execution.

        Returns True if lease was acquired, False if execution is already leased by another worker.
        """
        from app.models.workflow_delayed import ExecutionLease, LeaseStatus, DelayedExecution
        from datetime import timedelta

        now = datetime.utcnow()
        expires_at = now + timedelta(seconds=lease_duration_seconds)
        lease_key = f"lease_{execution_id}_{worker_id}"

        # First, try to expire any old leases for this execution
        await self.db.execute(
            text("""
                UPDATE execution_leases
                SET status = 'expired'
                WHERE delayed_execution_id = :exec_id
                AND status = 'leased'
                AND expires_at < :now
            """),
            {"exec_id": execution_id, "now": now}
        )

        # Now try to insert a new lease
        stmt = insert(ExecutionLease).values(
            delayed_execution_id=execution_id,
            lease_key=lease_key,
            worker_id=worker_id,
            status=LeaseStatus.leased,
            expires_at=expires_at,
        ).on_conflict_do_nothing(
            index_elements=["lease_key"]
        ).returning(ExecutionLease.id)

        result = await self.db.execute(stmt)
        return result.scalar_one_or_none() is not None


def generate_idempotency_key(*parts: Any) -> str:
    """
    Generate a deterministic idempotency key from parts.

    Args:
        *parts: Values to include in the key (will be sorted and hashed)

    Returns:
        SHA256 hash truncated to 32 characters
    """
    key_data = "|".join(str(p) for p in sorted(parts, key=str))
    return hashlib.sha256(key_data.encode()).hexdigest()[:32]