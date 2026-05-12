from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class QueueDeadLetter(Base):
    """Tasks that exhausted Celery retries; supports inspection and manual replay."""

    __tablename__ = "queue_dead_letters"

    id: Mapped[int] = mapped_column(primary_key=True, index=True)
    task_name: Mapped[str] = mapped_column(String(256), nullable=False, index=True)
    celery_task_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    args: Mapped[list | None] = mapped_column(JSONB, nullable=True)
    kwargs: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    exception_type: Mapped[str | None] = mapped_column(String(256), nullable=True)
    exception_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    traceback: Mapped[str | None] = mapped_column(Text, nullable=True)
    retries_at_failure: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_retries: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )
    replayed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    replay_note: Mapped[str | None] = mapped_column(Text, nullable=True)
