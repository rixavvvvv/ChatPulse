from celery import Celery

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "bulk_messaging",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["app.queue.tasks"],
)

celery_app.conf.update(
    task_default_queue=settings.celery_default_queue,
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    result_expires=settings.celery_result_ttl_seconds,
    task_track_started=True,
    broker_connection_retry_on_startup=True,
)
