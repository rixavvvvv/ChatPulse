import asyncio
import logging

from app.db import AsyncSessionLocal
from app.queue.celery_app import celery_app
from app.services.bulk_service import bulk_send_messages

logger = logging.getLogger(__name__)


async def _run_bulk_send(
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
) -> dict[str, int]:
    async with AsyncSessionLocal() as session:
        result = await bulk_send_messages(
            session=session,
            message_template=message_template,
            contact_ids=contact_ids,
            workspace_id=workspace_id,
        )
        return {
            "success_count": result.success_count,
            "failed_count": result.failed_count,
        }


@celery_app.task(name="bulk.send_messages")
def process_bulk_send_task(
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
) -> dict[str, int]:
    logger.info(
        "Queue task started workspace_id=%s contact_count=%s",
        workspace_id,
        len(contact_ids),
    )
    return asyncio.run(
        _run_bulk_send(
            workspace_id=workspace_id,
            message_template=message_template,
            contact_ids=contact_ids,
        )
    )
