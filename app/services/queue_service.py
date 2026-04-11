from datetime import UTC, datetime

from celery.result import AsyncResult
from kombu.exceptions import OperationalError

from app.queue.celery_app import celery_app
from app.queue.tasks import process_bulk_send_task, process_campaign_send_task
from app.schemas.bulk import BulkQueueEnqueueResponse, BulkQueueStatusResponse


def _build_scoped_job_id(workspace_id: int, task_id: str) -> str:
    return f"{workspace_id}:{task_id}"


def _parse_scoped_job_id(scoped_job_id: str) -> tuple[int, str]:
    parts = scoped_job_id.split(":", maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Invalid job_id format")

    workspace_id_str, task_id = parts
    workspace_id = int(workspace_id_str)
    if not task_id.strip():
        raise ValueError("Invalid job_id format")

    return workspace_id, task_id


def enqueue_bulk_send_job(
    workspace_id: int,
    message_template: str,
    contact_ids: list[int],
) -> BulkQueueEnqueueResponse:
    try:
        task = process_bulk_send_task.delay(
            workspace_id=workspace_id,
            message_template=message_template,
            contact_ids=contact_ids,
        )
    except OperationalError as exc:
        raise RuntimeError("Queue broker is unavailable") from exc

    return BulkQueueEnqueueResponse(
        job_id=_build_scoped_job_id(
            workspace_id=workspace_id, task_id=task.id),
        status="queued",
    )


def enqueue_campaign_job(
    workspace_id: int,
    campaign_id: int,
    schedule_at: datetime | None = None,
) -> BulkQueueEnqueueResponse:
    try:
        if schedule_at is not None:
            normalized_schedule = schedule_at
            if normalized_schedule.tzinfo is None:
                normalized_schedule = normalized_schedule.replace(tzinfo=UTC)
            else:
                normalized_schedule = normalized_schedule.astimezone(UTC)

            if normalized_schedule <= datetime.now(tz=UTC):
                task = process_campaign_send_task.delay(
                    workspace_id=workspace_id,
                    campaign_id=campaign_id,
                )
            else:
                task = process_campaign_send_task.apply_async(
                    kwargs={
                        "workspace_id": workspace_id,
                        "campaign_id": campaign_id,
                    },
                    eta=normalized_schedule,
                )
        else:
            task = process_campaign_send_task.delay(
                workspace_id=workspace_id,
                campaign_id=campaign_id,
            )
    except OperationalError as exc:
        raise RuntimeError("Queue broker is unavailable") from exc
    except Exception as exc:
        raise RuntimeError("Queue broker is unavailable") from exc

    return BulkQueueEnqueueResponse(
        job_id=_build_scoped_job_id(
            workspace_id=workspace_id,
            task_id=task.id,
        ),
        status="queued",
    )


def get_scoped_job_status(
    job_id: str,
    workspace_id: int,
) -> BulkQueueStatusResponse:
    try:
        encoded_workspace_id, task_id = _parse_scoped_job_id(job_id)
    except ValueError as exc:
        raise RuntimeError("Invalid job_id") from exc

    if encoded_workspace_id != workspace_id:
        raise RuntimeError("Job does not belong to current workspace")

    result = AsyncResult(task_id, app=celery_app)
    state = result.state.lower()

    if state == "success":
        payload = result.result if isinstance(result.result, dict) else {}
        return BulkQueueStatusResponse(
            job_id=job_id,
            status="success",
            success_count=int(payload.get("success_count", 0)),
            failed_count=int(payload.get("failed_count", 0)),
        )

    if state == "failure":
        error_message = str(result.result) if result.result else "Job failed"
        return BulkQueueStatusResponse(
            job_id=job_id,
            status="failure",
            error=error_message,
        )

    return BulkQueueStatusResponse(job_id=job_id, status=state)


def get_bulk_send_job_status(
    job_id: str,
    workspace_id: int,
) -> BulkQueueStatusResponse:
    return get_scoped_job_status(job_id=job_id, workspace_id=workspace_id)
