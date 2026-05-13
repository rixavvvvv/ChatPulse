"""
Trigger Event Dispatch Service

This service handles dispatching workflow triggers when domain events occur.
It integrates with the Celery task queue for async processing.
"""

import logging
from typing import Any

from app.queue.celery_app import celery_app
from app.services.trigger_matching_engine import TriggerMatchingEngine

logger = logging.getLogger(__name__)


async def dispatch_triggers_for_event(
    event_id: int,
    event_type: str,
    workspace_id: int,
    event_payload: dict[str, Any],
    correlation_id: str | None = None,
    trace_id: str | None = None,
) -> dict[str, Any]:
    """
    Dispatch trigger tasks for a domain event.

    This function is called when domain events are created and triggers
    the async matching and execution of workflows.
    """
    from app.queue.trigger_tasks import ProcessEventTask

    result = ProcessEventTask().apply_async(
        args=[event_id, event_type, workspace_id],
        kwargs={},
        queue="trigger_ingest",
    )

    return {
        "task_id": result.id,
        "event_id": event_id,
        "event_type": event_type,
        "workspace_id": workspace_id,
    }


def trigger_workflow_execution(
    trigger_id: int,
    event_id: int,
    dedupe_key: str,
) -> Any:
    """
    Trigger a workflow execution task.

    This is called from the trigger matching process to execute
    workflows for matched triggers.
    """
    from app.queue.trigger_tasks import ExecuteWorkflowTask

    result = ExecuteWorkflowTask().apply_async(
        args=[trigger_id, event_id, dedupe_key],
        kwargs={},
        queue="trigger_execution",
    )

    return result


async def process_domain_event(
    event_id: int,
    event_type: str,
    workspace_id: int,
    event_payload: dict[str, Any],
) -> list[int]:
    """
    Process a domain event and find matching triggers.

    Returns list of trigger IDs that were matched and dispatched.
    """
    from app.db import AsyncSessionLocal
    from app.services.trigger_matching_engine import TriggerMatchingEngine

    async with AsyncSessionLocal() as db:
        engine = TriggerMatchingEngine(db)
        matching_triggers = await engine.find_matching_triggers(
            event_type=event_type,
            workspace_id=workspace_id,
            event_payload=event_payload,
        )

        dispatched_trigger_ids = []
        for trigger in matching_triggers:
            from app.services.trigger_matching_engine import generate_dedupe_key

            dedupe_key = generate_dedupe_key(
                event_type=event_type,
                workspace_id=workspace_id,
                event_payload=event_payload,
                trigger_id=trigger.id,
            )

            result = trigger_workflow_execution(
                trigger_id=trigger.id,
                event_id=event_id,
                dedupe_key=dedupe_key,
            )

            dispatched_trigger_ids.append(trigger.id)
            logger.info(
                "Dispatched trigger execution task_id=%s trigger_id=%s event_id=%s",
                result.id,
                trigger.id,
                event_id,
            )

        return dispatched_trigger_ids