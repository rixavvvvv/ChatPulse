"""
Delayed Execution Service

This service handles scheduling, time calculation, and management of delayed workflow executions.
Supports fixed, relative, wait_until, and business-hours based delays.
"""

import hashlib
import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.workflow_delayed import (
    BusinessHoursConfig,
    DelayedExecution,
    DelayedExecutionMetrics,
    DelayedExecutionStatus,
    ExecutionLease,
    LeaseStatus,
)

logger = logging.getLogger(__name__)


def generate_execution_id() -> str:
    return f"delay_{uuid.uuid4().hex[:16]}"


def generate_idempotency_key(
    workspace_id: int,
    workflow_definition_id: int,
    trigger_data: dict[str, Any],
    delay_config: dict[str, Any],
) -> str:
    key_data = f"{workspace_id}:{workflow_definition_id}:{sorted(trigger_data.items())}:{sorted(delay_config.items())}"
    return f"delayed:{hashlib.sha256(key_data.encode()).hexdigest()[:32]}"


async def calculate_scheduled_time(
    db: AsyncSession,
    workspace_id: int,
    delay_type: str,
    delay_config: dict[str, Any],
    trigger_data: dict[str, Any],
) -> tuple[datetime, datetime | None, datetime | None]:
    """
    Calculate the scheduled execution time based on delay type and configuration.
    Returns (scheduled_at, window_start, window_end)
    """
    now = datetime.now(timezone.utc)

    if delay_type == "fixed":
        duration_seconds = delay_config.get("duration_seconds", 0)
        scheduled_at = now + timedelta(seconds=duration_seconds)
        return scheduled_at, None, None

    elif delay_type == "relative":
        field = delay_config.get("field")
        offset_seconds = delay_config.get("offset_seconds", 0)
        fallback_seconds = delay_config.get("fallback_seconds", 0)

        field_value = trigger_data.get(field)
        if field_value and isinstance(field_value, str):
            try:
                base_time = datetime.fromisoformat(field_value.replace("Z", "+00:00"))
                scheduled_at = base_time + timedelta(seconds=offset_seconds)
            except (ValueError, TypeError):
                scheduled_at = now + timedelta(seconds=fallback_seconds)
        else:
            scheduled_at = now + timedelta(seconds=fallback_seconds)

        return scheduled_at, None, None

    elif delay_type == "wait_until":
        timestamp_field = delay_config.get("timestamp_field")
        timezone_str = delay_config.get("timezone", "UTC")
        allow_past = delay_config.get("allow_past", True)

        timestamp_value = trigger_data.get(timestamp_field)
        if timestamp_value and isinstance(timestamp_value, str):
            try:
                scheduled_at = datetime.fromisoformat(timestamp_value.replace("Z", "+00:00"))
            except (ValueError, TypeError):
                scheduled_at = now
        else:
            scheduled_at = now

        if scheduled_at < now:
            if allow_past:
                return now, None, None
            else:
                return now + timedelta(hours=1), None, None

        return scheduled_at, None, None

    elif delay_type == "business_hours":
        timezone_str = delay_config.get("timezone", "UTC")
        window_hours = delay_config.get("window_hours", 2)

        scheduled_at = await _calculate_next_business_hours(db, workspace_id, timezone_str)

        window_start = scheduled_at
        window_end = scheduled_at + timedelta(hours=window_hours)

        return scheduled_at, window_start, window_end

    return now, None, None


async def _calculate_next_business_hours(
    db: AsyncSession,
    workspace_id: int,
    timezone_str: str,
) -> datetime:
    """Calculate the next available business hours slot."""
    import zoneinfo
    try:
        tz = zoneinfo.ZoneInfo(timezone_str)
    except KeyError:
        tz = timezone.utc

    now = datetime.now(tz)

    stmt = select(BusinessHoursConfig).where(
        and_(
            BusinessHoursConfig.workspace_id == workspace_id,
            BusinessHoursConfig.is_active == True,
        )
    )
    result = await db.execute(stmt)
    business_hours = list(result.scalars().all())

    if not business_hours:
        return now + timedelta(hours=1)

    for _ in range(14):
        current_day = now.weekday()
        current_time = now.time()

        matching_hours = [bh for bh in business_hours if bh.day_of_week == current_day]

        for bh in matching_hours:
            start_time = datetime.strptime(bh.start_time, "%H:%M").time()
            end_time = datetime.strptime(bh.end_time, "%H:%M").time()

            if current_time < start_time:
                next_slot = now.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)
                return next_slot
            elif current_time < end_time:
                return now
            else:
                now = now + timedelta(days=1)
                now = now.replace(hour=0, minute=0, second=0, microsecond=0)
                break
        else:
            now = now + timedelta(days=1)
            now = now.replace(hour=0, minute=0, second=0, microsecond=0)

    return now


async def create_delayed_execution(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int,
    delay_type: str,
    delay_config: dict[str, Any],
    context: dict[str, Any],
    trigger_data: dict[str, Any],
    max_retries: int = 3,
    idempotency_key: str | None = None,
) -> DelayedExecution:
    if not idempotency_key:
        idempotency_key = generate_idempotency_key(
            workspace_id, workflow_definition_id, trigger_data, delay_config
        )

    existing = await db.execute(
        select(DelayedExecution).where(
            and_(
                DelayedExecution.idempotency_key == idempotency_key,
                DelayedExecution.status.in_([
                    DelayedExecutionStatus.scheduled,
                    DelayedExecutionStatus.pending,
                    DelayedExecutionStatus.running,
                ]),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Duplicate delayed execution exists")

    scheduled_at, window_start, window_end = await calculate_scheduled_time(
        db, workspace_id, delay_type, delay_config, trigger_data
    )

    execution = DelayedExecution(
        workspace_id=workspace_id,
        workflow_definition_id=workflow_definition_id,
        execution_id=generate_execution_id(),
        delay_type=delay_type,
        delay_config=delay_config,
        scheduled_at=scheduled_at,
        window_start=window_start,
        window_end=window_end,
        status=DelayedExecutionStatus.scheduled,
        context=context,
        trigger_data=trigger_data,
        idempotency_key=idempotency_key,
        max_retries=max_retries,
    )

    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def get_delayed_execution(
    db: AsyncSession,
    execution_id: str,
    workspace_id: int,
) -> DelayedExecution | None:
    stmt = select(DelayedExecution).where(
        and_(
            DelayedExecution.execution_id == execution_id,
            DelayedExecution.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def get_delayed_execution_by_id(
    db: AsyncSession,
    execution_id: int,
    workspace_id: int,
) -> DelayedExecution | None:
    return await db.get(DelayedExecution, execution_id)


async def list_delayed_executions(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int | None = None,
    status: DelayedExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[DelayedExecution], int]:
    query = select(DelayedExecution).where(DelayedExecution.workspace_id == workspace_id)

    if workflow_definition_id:
        query = query.where(DelayedExecution.workflow_definition_id == workflow_definition_id)
    if status:
        query = query.where(DelayedExecution.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(DelayedExecution.scheduled_at.asc()).offset(offset).limit(limit)
    result = await db.execute(query)
    executions = list(result.scalars().all())

    return executions, total


async def get_pending_delayed_executions(
    db: AsyncSession,
    limit: int = 100,
) -> list[DelayedExecution]:
    now = datetime.now(timezone.utc)

    stmt = (
        select(DelayedExecution)
        .where(
            and_(
                DelayedExecution.status == DelayedExecutionStatus.scheduled,
                DelayedExecution.scheduled_at <= now,
            )
        )
        .order_by(DelayedExecution.scheduled_at.asc())
        .limit(limit)
    )
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def update_delayed_execution(
    db: AsyncSession,
    execution: DelayedExecution,
    status: DelayedExecutionStatus | None = None,
    workflow_execution_id: int | None = None,
    error: str | None = None,
    started_at: datetime | None = None,
    completed_at: datetime | None = None,
    retry_count: int | None = None,
) -> DelayedExecution:
    if status:
        execution.status = status
    if workflow_execution_id:
        execution.workflow_execution_id = workflow_execution_id
    if error is not None:
        execution.error = error
    if started_at:
        execution.started_at = started_at
    if completed_at:
        execution.completed_at = completed_at
    if retry_count is not None:
        execution.retry_count = retry_count

    execution.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(execution)
    return execution


async def cancel_delayed_execution(
    db: AsyncSession,
    execution: DelayedExecution,
) -> DelayedExecution:
    if execution.status in [DelayedExecutionStatus.completed, DelayedExecutionStatus.running]:
        raise ValueError(f"Cannot cancel execution in status: {execution.status}")

    return await update_delayed_execution(
        db, execution, status=DelayedExecutionStatus.cancelled
    )


async def acquire_lease(
    db: AsyncSession,
    delayed_execution_id: int,
    worker_id: str,
    lease_duration_seconds: int = 300,
) -> ExecutionLease | None:
    """Acquire a lease for executing a delayed execution."""
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=lease_duration_seconds)

    existing_lease = await db.execute(
        select(ExecutionLease).where(
            and_(
                ExecutionLease.delayed_execution_id == delayed_execution_id,
                ExecutionLease.status == LeaseStatus.leased,
                ExecutionLease.expires_at > now,
            )
        )
    )
    if existing_lease.scalar_one_or_none():
        return None

    lease_key = f"lease_{delayed_execution_id}_{worker_id}"

    lease = ExecutionLease(
        delayed_execution_id=delayed_execution_id,
        lease_key=lease_key,
        worker_id=worker_id,
        status=LeaseStatus.leased,
        expires_at=expires_at,
    )

    db.add(lease)
    await db.commit()
    await db.refresh(lease)
    return lease


async def release_lease(
    db: AsyncSession,
    lease: ExecutionLease,
) -> ExecutionLease:
    lease.status = LeaseStatus.released
    lease.released_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(lease)
    return lease


async def expire_old_leases(db: AsyncSession) -> int:
    """Expire leases that have passed their expiration time."""
    now = datetime.now(timezone.utc)

    result = await db.execute(
        update(ExecutionLease)
        .where(
            and_(
                ExecutionLease.status == LeaseStatus.leased,
                ExecutionLease.expires_at <= now,
            )
        )
        .values(status=LeaseStatus.expired)
    )
    await db.commit()
    return result.rowcount


async def get_delayed_execution_stats(
    db: AsyncSession,
    workspace_id: int,
    workflow_definition_id: int | None = None,
) -> dict[str, Any]:
    query = select(DelayedExecution).where(DelayedExecution.workspace_id == workspace_id)

    if workflow_definition_id:
        query = query.where(DelayedExecution.workflow_definition_id == workflow_definition_id)

    result = await db.execute(query)
    executions = list(result.scalars().all())

    total = len(executions)
    scheduled = sum(1 for e in executions if e.status == DelayedExecutionStatus.scheduled)
    completed = sum(1 for e in executions if e.status == DelayedExecutionStatus.completed)
    failed = sum(1 for e in executions if e.status == DelayedExecutionStatus.failed)
    running = sum(1 for e in executions if e.status == DelayedExecutionStatus.running)
    expired = sum(1 for e in executions if e.status == DelayedExecutionStatus.expired)

    delay_seconds = []
    for e in executions:
        if e.started_at and e.created_at:
            delay = (e.started_at - e.created_at).total_seconds()
            if delay > 0:
                delay_seconds.append(delay)

    avg_delay = sum(delay_seconds) / len(delay_seconds) if delay_seconds else None

    return {
        "total_scheduled": total,
        "scheduled": scheduled,
        "completed": completed,
        "failed": failed,
        "running": running,
        "expired": expired,
        "avg_delay_seconds": avg_delay,
    }


async def create_business_hours(
    db: AsyncSession,
    workspace_id: int,
    timezone: str,
    day_of_week: int,
    start_time: str,
    end_time: str,
    is_active: bool = True,
) -> BusinessHoursConfig:
    config = BusinessHoursConfig(
        workspace_id=workspace_id,
        timezone=timezone,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        is_active=is_active,
    )
    db.add(config)
    await db.commit()
    await db.refresh(config)
    return config


async def list_business_hours(
    db: AsyncSession,
    workspace_id: int,
) -> list[BusinessHoursConfig]:
    stmt = select(BusinessHoursConfig).where(BusinessHoursConfig.workspace_id == workspace_id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


async def delete_business_hours(
    db: AsyncSession,
    config_id: int,
    workspace_id: int,
) -> None:
    config = await db.get(BusinessHoursConfig, config_id)
    if config and config.workspace_id == workspace_id:
        await db.delete(config)
        await db.commit()