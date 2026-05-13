"""
Conversation State Engine

Manages conversation lifecycle state transitions with optimistic locking.
State machine: open → assigned → resolved → closed (with reopen paths).
"""

import logging
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.conversation import Conversation, ConversationStatus

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# State Transition Rules
# ──────────────────────────────────────────────────────────

# Maps current_status → set of valid target statuses
VALID_TRANSITIONS: dict[ConversationStatus, set[ConversationStatus]] = {
    ConversationStatus.open: {
        ConversationStatus.assigned,
        ConversationStatus.resolved,
        ConversationStatus.closed,
    },
    ConversationStatus.assigned: {
        ConversationStatus.open,       # Unassign
        ConversationStatus.resolved,
        ConversationStatus.closed,
    },
    ConversationStatus.resolved: {
        ConversationStatus.open,       # Reopen
        ConversationStatus.closed,
    },
    ConversationStatus.closed: {
        ConversationStatus.open,       # Reopen
    },
}


class StaleVersionError(Exception):
    """Raised when optimistic locking detects a concurrent modification."""

    def __init__(self, expected_version: int, actual_version: int):
        self.expected_version = expected_version
        self.actual_version = actual_version
        super().__init__(
            f"Conversation version conflict: expected {expected_version}, "
            f"found {actual_version}. Another agent modified this conversation."
        )


class InvalidTransitionError(Exception):
    """Raised when a state transition is not allowed."""

    def __init__(self, current: ConversationStatus, target: ConversationStatus):
        self.current = current
        self.target = target
        super().__init__(
            f"Invalid state transition: {current.value} → {target.value}"
        )


def can_transition(
    current: ConversationStatus,
    target: ConversationStatus,
) -> bool:
    """Check if a state transition is valid."""
    valid = VALID_TRANSITIONS.get(current, set())
    return target in valid


async def transition_state(
    db: AsyncSession,
    conversation: Conversation,
    target_status: ConversationStatus,
    expected_version: int,
    actor_user_id: int | None = None,
) -> Conversation:
    """
    Transition conversation to a new state with optimistic locking.

    1. Validate the state transition is allowed
    2. Check version matches (optimistic lock)
    3. Apply state change + side effects
    4. Increment version
    5. Commit

    Raises:
        InvalidTransitionError: If the transition is not allowed
        StaleVersionError: If another agent modified the conversation concurrently
    """
    current_status = conversation.status

    # Validate transition
    if not can_transition(current_status, target_status):
        raise InvalidTransitionError(current_status, target_status)

    # Optimistic locking check
    if conversation.version != expected_version:
        raise StaleVersionError(expected_version, conversation.version)

    now = datetime.now(timezone.utc)

    # Apply state-specific side effects
    conversation.status = target_status
    conversation.version += 1
    conversation.updated_at = now

    if target_status == ConversationStatus.resolved:
        conversation.resolved_at = now
    elif target_status == ConversationStatus.closed:
        conversation.closed_at = now
    elif target_status == ConversationStatus.open:
        # Reopening clears resolved/closed timestamps
        conversation.resolved_at = None
        conversation.closed_at = None

    await db.commit()
    await db.refresh(conversation)

    logger.info(
        "Conversation %d transitioned: %s → %s (v%d→v%d) by user %s",
        conversation.id,
        current_status.value,
        target_status.value,
        expected_version,
        conversation.version,
        actor_user_id,
    )

    return conversation


async def reopen_on_new_message(
    db: AsyncSession,
    conversation: Conversation,
) -> Conversation:
    """
    Auto-reopen a resolved/closed conversation when a new inbound message arrives.

    Bypasses version check since this is a system-initiated action.
    """
    if conversation.status in (ConversationStatus.resolved, ConversationStatus.closed):
        now = datetime.now(timezone.utc)
        conversation.status = ConversationStatus.open
        conversation.version += 1
        conversation.updated_at = now
        conversation.resolved_at = None
        conversation.closed_at = None

        await db.commit()
        await db.refresh(conversation)

        logger.info(
            "Conversation %d auto-reopened on new inbound message (v%d)",
            conversation.id,
            conversation.version,
        )

    return conversation
