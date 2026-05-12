from __future__ import annotations

import asyncio
import logging
import traceback
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.db import AsyncSessionLocal, engine
from app.models.queue_dead_letter import QueueDeadLetter

logger = logging.getLogger(__name__)


async def _dispose_engine() -> None:
    await engine.dispose()


async def persist_dead_letter(
    session: AsyncSession,
    *,
    task_name: str,
    celery_task_id: str | None,
    args: tuple[Any, ...] | list[Any] | None,
    kwargs: dict[str, Any] | None,
    exception: BaseException,
    tb: str | None,
    retries_at_failure: int | None,
    max_retries: int | None,
) -> None:
    row = QueueDeadLetter(
        task_name=task_name,
        celery_task_id=celery_task_id,
        args=list(args) if isinstance(args, tuple) else args,
        kwargs=kwargs,
        exception_type=type(exception).__name__,
        exception_message=str(exception),
        traceback=tb,
        retries_at_failure=retries_at_failure,
        max_retries=max_retries,
    )
    session.add(row)
    await session.commit()


def persist_dead_letter_sync(
    *,
    task_name: str,
    celery_task_id: str | None,
    args: tuple[Any, ...] | list[Any] | None,
    kwargs: dict[str, Any] | None,
    exception: BaseException,
    einfo: Any | None = None,
    retries_at_failure: int | None = None,
    max_retries: int | None = None,
) -> None:
    """Called from Celery task context (sync); opens a short async session."""

    tb_str: str | None = None
    if einfo is not None and getattr(einfo, "traceback", None) is not None:
        tb_str = "".join(traceback.format_tb(einfo.tb)) + str(einfo)
    elif einfo is not None:
        tb_str = str(einfo)

    async def _runner() -> None:
        try:
            async with AsyncSessionLocal() as session:
                await persist_dead_letter(
                    session,
                    task_name=task_name,
                    celery_task_id=celery_task_id,
                    args=args,
                    kwargs=kwargs,
                    exception=exception,
                    tb=tb_str,
                    retries_at_failure=retries_at_failure,
                    max_retries=max_retries,
                )
        finally:
            try:
                await _dispose_engine()
            except Exception as exc:  # pragma: no cover
                logger.warning("DLQ engine dispose failed: %s", exc)

    asyncio.run(_runner())
