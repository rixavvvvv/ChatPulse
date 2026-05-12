"""Central registry for Celery queue names and task routing (BullMQ-style topology)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class QueueNames:
    """Physical Redis queue names — run workers with `-Q` covering queues you need."""

    bulk_messages: str = "bulk-messages"
    webhooks: str = "webhooks"
    imports: str = "imports"
    analytics: str = "analytics"
    campaigns_schedule: str = "campaigns-schedule"


@dataclass(frozen=True, slots=True)
class TaskNames:
    """Stable Celery task names for routing, DLQ filtering, and monitoring."""

    bulk_send_messages: str = "bulk.send_messages"
    campaign_send: str = "campaign.send"
    webhook_process_ingestion: str = "webhooks.process_ingestion"
    campaign_recovery_check: str = "campaign.recovery.check"
    campaign_recovery_manual: str = "campaign.recovery.manual"


QUEUES = QueueNames()
TASKS = TaskNames()


def celery_task_routes() -> dict[str, dict[str, Any]]:
    """Route long-running / bursty families to dedicated queues."""
    from app.core.config import get_settings

    q = get_settings().celery_webhook_queue.strip()
    return {
        TASKS.webhook_process_ingestion: {"queue": q},
    }


def default_worker_queue_spec(settings_celery_default_queue: str, settings_webhook_queue: str) -> str:
    """Comma-separated `-Q` argument for a worker handling default + webhook queues."""
    return f"{settings_celery_default_queue},{settings_webhook_queue}"
