"""
Ecommerce Automation Service

This service handles the creation, management, and execution of ecommerce automations.
Integrates with Shopify webhooks, workflow runtime, delayed execution, and segmentation.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import and_, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.ecommerce_automation import (
    AttributionModel,
    AutomationTriggerType,
    EcommerceAutomation,
    EcommerceAutomationExecution,
    EcommerceAutomationMetrics,
    EcommerceAttribution,
    EcommerceAutomationStatus,
    ExecutionStatus,
)

logger = logging.getLogger(__name__)


def generate_execution_id() -> str:
    return f"ecom_auto_{uuid.uuid4().hex[:16]}"


async def get_automation_by_id(
    db: AsyncSession,
    automation_id: int,
    workspace_id: int,
) -> EcommerceAutomation | None:
    stmt = select(EcommerceAutomation).where(
        and_(
            EcommerceAutomation.id == automation_id,
            EcommerceAutomation.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_automations(
    db: AsyncSession,
    workspace_id: int,
    automation_type: str | None = None,
    trigger_type: str | None = None,
    status: EcommerceAutomationStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[EcommerceAutomation], int]:
    query = select(EcommerceAutomation).where(EcommerceAutomation.workspace_id == workspace_id)

    if automation_type:
        query = query.where(EcommerceAutomation.automation_type == automation_type)
    if trigger_type:
        query = query.where(EcommerceAutomation.trigger_type == trigger_type)
    if status:
        query = query.where(EcommerceAutomation.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(EcommerceAutomation.priority.desc(), EcommerceAutomation.created_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    automations = list(result.scalars().all())

    return automations, total


async def create_automation(
    db: AsyncSession,
    workspace_id: int,
    name: str,
    description: str | None,
    automation_type: str,
    trigger_config: dict[str, Any],
    action_config: dict[str, Any],
    delay_seconds: int = 0,
    delay_type: str | None = None,
    segment_id: int | None = None,
    template_id: int | None = None,
    priority: int = 0,
    max_retries: int = 3,
    created_by: int = 0,
) -> EcommerceAutomation:
    trigger_type = trigger_config.get("trigger_type", "manual")

    automation = EcommerceAutomation(
        workspace_id=workspace_id,
        name=name,
        description=description,
        automation_type=automation_type,
        trigger_type=trigger_type,
        trigger_config=trigger_config,
        action_config=action_config,
        delay_seconds=delay_seconds,
        delay_type=delay_type,
        segment_id=segment_id,
        template_id=template_id,
        priority=priority,
        max_retries=max_retries,
        created_by=created_by,
    )

    db.add(automation)
    await db.commit()
    await db.refresh(automation)
    return automation


async def update_automation(
    db: AsyncSession,
    automation: EcommerceAutomation,
    name: str | None = None,
    description: str | None = None,
    status: EcommerceAutomationStatus | None = None,
    trigger_config: dict[str, Any] | None = None,
    action_config: dict[str, Any] | None = None,
    delay_seconds: int | None = None,
    delay_type: str | None = None,
    segment_id: int | None = None,
    template_id: int | None = None,
    priority: int | None = None,
    max_retries: int | None = None,
) -> EcommerceAutomation:
    if name is not None:
        automation.name = name
    if description is not None:
        automation.description = description
    if status is not None:
        automation.status = status
    if trigger_config is not None:
        automation.trigger_config = trigger_config
    if action_config is not None:
        automation.action_config = action_config
    if delay_seconds is not None:
        automation.delay_seconds = delay_seconds
    if delay_type is not None:
        automation.delay_type = delay_type
    if segment_id is not None:
        automation.segment_id = segment_id
    if template_id is not None:
        automation.template_id = template_id
    if priority is not None:
        automation.priority = priority
    if max_retries is not None:
        automation.max_retries = max_retries

    automation.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(automation)
    return automation


async def delete_automation(db: AsyncSession, automation: EcommerceAutomation) -> None:
    await db.delete(automation)
    await db.commit()


async def create_execution(
    db: AsyncSession,
    workspace_id: int,
    automation_id: int,
    order_id: str | None,
    cart_id: str | None,
    contact_id: int | None,
    trigger_data: dict[str, Any],
) -> EcommerceAutomationExecution:
    existing = await db.execute(
        select(EcommerceAutomationExecution).where(
            and_(
                EcommerceAutomationExecution.automation_id == automation_id,
                EcommerceAutomationExecution.order_id == order_id,
                EcommerceAutomationExecution.status.in_([
                    ExecutionStatus.pending,
                    ExecutionStatus.scheduled,
                    ExecutionStatus.sent,
                ]),
            )
        )
    )
    if existing.scalar_one_or_none():
        raise ValueError("Duplicate execution exists for this order")

    execution = EcommerceAutomationExecution(
        workspace_id=workspace_id,
        automation_id=automation_id,
        order_id=order_id,
        cart_id=cart_id,
        contact_id=contact_id,
        execution_id=generate_execution_id(),
        status=ExecutionStatus.pending,
        trigger_data=trigger_data,
        message_payload={},
    )

    db.add(execution)
    await db.commit()
    await db.refresh(execution)
    return execution


async def get_execution(
    db: AsyncSession,
    execution_id: str,
    workspace_id: int,
) -> EcommerceAutomationExecution | None:
    stmt = select(EcommerceAutomationExecution).where(
        and_(
            EcommerceAutomationExecution.execution_id == execution_id,
            EcommerceAutomationExecution.workspace_id == workspace_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def list_executions(
    db: AsyncSession,
    workspace_id: int,
    automation_id: int | None = None,
    status: ExecutionStatus | None = None,
    limit: int = 50,
    offset: int = 0,
) -> tuple[list[EcommerceAutomationExecution], int]:
    query = select(EcommerceAutomationExecution).where(
        EcommerceAutomationExecution.workspace_id == workspace_id
    )

    if automation_id:
        query = query.where(EcommerceAutomationExecution.automation_id == automation_id)
    if status:
        query = query.where(EcommerceAutomationExecution.status == status)

    count_query = select(func.count()).select_from(query.subquery())
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0

    query = query.order_by(EcommerceAutomationExecution.created_at.desc())
    query = query.offset(offset).limit(limit)
    result = await db.execute(query)
    executions = list(result.scalars().all())

    return executions, total


async def update_execution(
    db: AsyncSession,
    execution: EcommerceAutomationExecution,
    status: ExecutionStatus | None = None,
    message_id: str | None = None,
    message_payload: dict[str, Any] | None = None,
    delayed_execution_id: int | None = None,
    error: str | None = None,
    sent_at: datetime | None = None,
    delivered_at: datetime | None = None,
    retry_count: int | None = None,
) -> EcommerceAutomationExecution:
    if status:
        execution.status = status
    if message_id:
        execution.message_id = message_id
    if message_payload:
        execution.message_payload = message_payload
    if delayed_execution_id:
        execution.delayed_execution_id = delayed_execution_id
    if error is not None:
        execution.error = error
    if sent_at:
        execution.sent_at = sent_at
    if delivered_at:
        execution.delivered_at = delivered_at
    if retry_count is not None:
        execution.retry_count = retry_count

    execution.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(execution)
    return execution


async def get_pending_automations(
    db: AsyncSession,
    trigger_type: str,
    workspace_id: int,
) -> list[EcommerceAutomation]:
    stmt = select(EcommerceAutomation).where(
        and_(
            EcommerceAutomation.workspace_id == workspace_id,
            EcommerceAutomation.trigger_type == trigger_type,
            EcommerceAutomation.status == EcommerceAutomationStatus.active,
        )
    ).order_by(EcommerceAutomation.priority.desc())

    result = await db.execute(stmt)
    return list(result.scalars().all())


async def get_automation_stats(
    db: AsyncSession,
    workspace_id: int,
    automation_id: int | None = None,
) -> dict[str, Any]:
    query = select(EcommerceAutomation).where(EcommerceAutomation.workspace_id == workspace_id)
    if automation_id:
        query = query.where(EcommerceAutomation.id == automation_id)

    result = await db.execute(query)
    automations = list(result.scalars().all())

    total = len(automations)
    active = sum(1 for a in automations if a.status == EcommerceAutomationStatus.active)
    paused = sum(1 for a in automations if a.status == EcommerceAutomationStatus.paused)

    exec_query = select(EcommerceAutomationExecution).where(
        EcommerceAutomationExecution.workspace_id == workspace_id
    )
    exec_result = await db.execute(exec_query)
    executions = list(exec_result.scalars().all())

    sent = sum(1 for e in executions if e.status == ExecutionStatus.sent)
    delivered = sum(1 for e in executions if e.status == ExecutionStatus.delivered)
    failed = sum(1 for e in executions if e.status == ExecutionStatus.failed)

    return {
        "total_automations": total,
        "active_automations": active,
        "paused_automations": paused,
        "total_executions": len(executions),
        "sent_count": sent,
        "delivered_count": delivered,
        "failed_count": failed,
    }


async def get_abandoned_cart_recovery_metrics(
    db: AsyncSession,
    workspace_id: int,
    days: int = 30,
) -> dict[str, Any]:
    from datetime import timedelta

    cutoff = datetime.now(timezone.utc) - timedelta(days=days)

    cart_executions = await db.execute(
        select(EcommerceAutomationExecution).where(
            and_(
                EcommerceAutomationExecution.workspace_id == workspace_id,
                EcommerceAutomationExecution.created_at >= cutoff,
            )
        )
    )
    executions = list(cart_executions.scalars().all())

    abandoned_count = len(executions)
    recovery_attempts = sum(1 for e in executions if e.status in [ExecutionStatus.sent, ExecutionStatus.scheduled])
    recovered = sum(1 for e in executions if e.status == ExecutionStatus.delivered)

    recovery_rate = (recovered / abandoned_count * 100) if abandoned_count > 0 else 0

    return {
        "carts_abandoned": abandoned_count,
        "recovery_attempts": recovery_attempts,
        "recovered_orders": recovered,
        "recovery_rate": recovery_rate,
    }


async def create_attribution(
    db: AsyncSession,
    workspace_id: int,
    contact_id: int,
    order_id: str,
    cart_id: str | None,
    attribution_model: str,
    touchpoints: list[dict[str, Any]],
    revenue: float,
    currency: str = "USD",
) -> EcommerceAttribution:
    first_touch = touchpoints[0] if touchpoints else None
    last_touch = touchpoints[-1] if touchpoints else None

    attribution = EcommerceAttribution(
        workspace_id=workspace_id,
        contact_id=contact_id,
        order_id=order_id,
        cart_id=cart_id,
        attribution_model=attribution_model,
        touchpoints=touchpoints,
        revenue=revenue,
        currency=currency,
        first_touch_id=first_touch.get("execution_id") if first_touch else None,
        last_touch_id=last_touch.get("execution_id") if last_touch else None,
    )

    db.add(attribution)
    await db.commit()
    await db.refresh(attribution)
    return attribution


async def update_attribution_conversion(
    db: AsyncSession,
    order_id: str,
    contact_id: int,
    revenue: float,
) -> EcommerceAttribution | None:
    stmt = select(EcommerceAttribution).where(
        and_(
            EcommerceAttribution.order_id == order_id,
            EcommerceAttribution.contact_id == contact_id,
        )
    )
    result = await db.execute(stmt)
    attribution = result.scalar_one_or_none()

    if attribution:
        attribution.converted = True
        attribution.conversion_timestamp = datetime.now(timezone.utc)
        attribution.revenue = revenue
        await db.commit()
        await db.refresh(attribution)

    return attribution


async def get_attribution_by_order(
    db: AsyncSession,
    order_id: str,
    contact_id: int,
) -> EcommerceAttribution | None:
    stmt = select(EcommerceAttribution).where(
        and_(
            EcommerceAttribution.order_id == order_id,
            EcommerceAttribution.contact_id == contact_id,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def add_touchpoint(
    db: AsyncSession,
    order_id: str,
    contact_id: int,
    execution_id: str,
    touchpoint_type: str,
    automation_type: str,
    timestamp: datetime | None = None,
) -> EcommerceAttribution | None:
    attribution = await get_attribution_by_order(db, order_id, contact_id)

    if not attribution:
        return None

    touchpoint = {
        "execution_id": execution_id,
        "type": touchpoint_type,
        "automation_type": automation_type,
        "timestamp": (timestamp or datetime.now(timezone.utc)).isoformat(),
    }

    attribution.touchpoints.append(touchpoint)

    if not attribution.last_touch_id:
        attribution.first_touch_id = execution_id
    attribution.last_touch_id = execution_id

    await db.commit()
    await db.refresh(attribution)
    return attribution