from celery import Celery

from app.core.config import get_settings
from app.queue.registry import celery_task_routes

settings = get_settings()

celery_app = Celery(
    "bulk_messaging",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.queue.tasks", "app.queue.webhook_tasks"],
)

celery_app.conf.update(
    task_default_queue=settings.celery_default_queue,
    task_routes=celery_task_routes(),
    task_create_missing_queues=True,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=settings.celery_result_ttl_seconds,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_send_sent_event=True,
    worker_send_task_events=True,
)
