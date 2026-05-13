"""
Ecommerce Automation Orchestrator Service

Bridges Shopify webhook events → automation matching → execution dispatch.
Handles the full lifecycle from event ingestion to message delivery.
"""

import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.contact import Contact
from app.models.ecommerce_automation import (
    AutomationTriggerType,
    EcommerceAutomation,
    EcommerceAutomationStatus,
    ExecutionStatus,
)
from app.services import ecommerce_automation_service
from app.services import delayed_execution_service

logger = logging.getLogger(__name__)


# ──────────────────────────────────────────────────────────
# Trigger type mapping from Shopify topic → internal trigger
# ──────────────────────────────────────────────────────────

SHOPIFY_TOPIC_TO_TRIGGER: dict[str, AutomationTriggerType] = {
    "orders/create": AutomationTriggerType.order_created,
    "orders/cancelled": AutomationTriggerType.order_cancelled,
    "checkouts/update": AutomationTriggerType.cart_abandoned,
    "carts/update": AutomationTriggerType.cart_abandoned,
    "fulfillments/create": AutomationTriggerType.shipment_created,
    "fulfillments/update": AutomationTriggerType.shipment_delivered,
    "orders/fulfilled": AutomationTriggerType.order_fulfilled,
    "orders/paid": AutomationTriggerType.payment_received,
}


async def resolve_contact_by_phone(
    db: AsyncSession,
    workspace_id: int,
    phone: str,
) -> Contact | None:
    """Find or None a contact by phone within a workspace."""
    stmt = select(Contact).where(
        and_(
            Contact.workspace_id == workspace_id,
            Contact.phone == phone,
        )
    )
    result = await db.execute(stmt)
    return result.scalar_one_or_none()


async def process_shopify_event(
    db: AsyncSession,
    workspace_id: int,
    shopify_topic: str,
    payload: dict[str, Any],
    store_identifier: str | None = None,
) -> dict[str, Any]:
    """
    Main orchestration entry point.

    1. Map Shopify topic to internal trigger type
    2. Find active automations matching the trigger
    3. Validate segment membership if configured
    4. Check for cart-to-order conversion (cancel pending recovery)
    5. Create execution records
    6. Dispatch immediate or delayed execution
    7. Track attribution touchpoints
    """
    trigger_type = SHOPIFY_TOPIC_TO_TRIGGER.get(shopify_topic)
    if not trigger_type:
        logger.warning(
            "Unmapped Shopify topic: %s for workspace %d",
            shopify_topic, workspace_id,
        )
        return {"status": "skipped", "reason": f"unmapped_topic:{shopify_topic}"}

    # Extract customer info from payload
    customer = payload.get("customer", {})
    phone = customer.get("phone") or _extract_phone_from_payload(payload)

    if not phone:
        return {"status": "skipped", "reason": "no_customer_phone"}

    # Resolve contact
    contact = await resolve_contact_by_phone(db, workspace_id, phone)
    contact_id = contact.id if contact else None

    # Handle cart-to-order conversion: cancel pending abandoned cart recovery
    if trigger_type == AutomationTriggerType.order_created:
        cart_id = payload.get("cart_token") or payload.get("cart_id")
        if cart_id:
            await _cancel_pending_cart_recovery(db, workspace_id, cart_id)

    # Detect COD orders
    if trigger_type == AutomationTriggerType.order_created:
        payment_method = _extract_payment_method(payload)
        if payment_method and payment_method.lower() in ("cod", "cash_on_delivery"):
            trigger_type = AutomationTriggerType.cod_pending

    # Detect delivered status in fulfillment updates
    if trigger_type == AutomationTriggerType.shipment_delivered:
        shipment_status = payload.get("shipment_status", "").lower()
        if shipment_status not in ("delivered", "out_for_delivery"):
            trigger_type = AutomationTriggerType.shipment_created

    # Find matching automations
    automations = await ecommerce_automation_service.get_pending_automations(
        db, trigger_type.value, workspace_id
    )

    if not automations:
        return {"status": "no_matching_automations", "trigger_type": trigger_type.value}

    results = []
    for automation in automations:
        try:
            result = await _dispatch_automation(
                db=db,
                workspace_id=workspace_id,
                automation=automation,
                payload=payload,
                contact_id=contact_id,
                phone=phone,
            )
            results.append(result)
        except Exception as exc:
            logger.error(
                "Automation dispatch failed: automation_id=%d workspace=%d error=%s",
                automation.id, workspace_id, exc,
            )
            results.append({
                "automation_id": automation.id,
                "status": "error",
                "error": str(exc),
            })

    await db.commit()

    return {
        "status": "processed",
        "trigger_type": trigger_type.value,
        "automations_matched": len(automations),
        "results": results,
    }


async def _dispatch_automation(
    db: AsyncSession,
    workspace_id: int,
    automation: EcommerceAutomation,
    payload: dict[str, Any],
    contact_id: int | None,
    phone: str,
) -> dict[str, Any]:
    """Create execution and dispatch (immediate or delayed)."""
    order_id = str(payload.get("id", "")) if payload.get("id") else None
    cart_id = payload.get("cart_token") or payload.get("cart_id")

    # Create execution record
    execution = await ecommerce_automation_service.create_execution(
        db,
        workspace_id=workspace_id,
        automation_id=automation.id,
        order_id=order_id,
        cart_id=cart_id,
        contact_id=contact_id,
        trigger_data=payload,
    )

    # Delayed execution
    if automation.delay_seconds > 0:
        delayed = await delayed_execution_service.create_delayed_execution(
            db,
            workspace_id=workspace_id,
            workflow_definition_id=0,  # Ecommerce automations use 0
            delay_type=automation.delay_type or "fixed",
            delay_config={"duration_seconds": automation.delay_seconds},
            context={
                "execution_id": execution.execution_id,
                "automation_id": automation.id,
                "phone": phone,
            },
            trigger_data=payload,
            max_retries=automation.max_retries,
        )
        await ecommerce_automation_service.update_execution(
            db, execution,
            status=ExecutionStatus.scheduled,
            delayed_execution_id=delayed.id,
        )
        return {
            "automation_id": automation.id,
            "execution_id": execution.execution_id,
            "status": "scheduled",
            "delay_seconds": automation.delay_seconds,
        }

    # Immediate execution via Celery task
    from app.queue.ecommerce_automation_tasks import execute_automation
    execute_automation.apply_async(
        kwargs={"execution_id": execution.execution_id},
        queue="ecommerce_execution",
    )

    return {
        "automation_id": automation.id,
        "execution_id": execution.execution_id,
        "status": "dispatched",
    }


async def _cancel_pending_cart_recovery(
    db: AsyncSession,
    workspace_id: int,
    cart_id: str,
) -> int:
    """Cancel any pending abandoned cart recovery executions for this cart."""
    from app.models.ecommerce_automation import EcommerceAutomationExecution

    stmt = select(EcommerceAutomationExecution).where(
        and_(
            EcommerceAutomationExecution.workspace_id == workspace_id,
            EcommerceAutomationExecution.cart_id == cart_id,
            EcommerceAutomationExecution.status.in_([
                ExecutionStatus.pending,
                ExecutionStatus.scheduled,
            ]),
        )
    )
    result = await db.execute(stmt)
    pending_executions = list(result.scalars().all())

    cancelled = 0
    for execution in pending_executions:
        execution.status = ExecutionStatus.cancelled
        execution.error = "Cart converted to order"
        execution.updated_at = datetime.now(timezone.utc)
        cancelled += 1

        # Also cancel any associated delayed executions
        if execution.delayed_execution_id:
            delayed = await db.get(
                delayed_execution_service.DelayedExecution,
                execution.delayed_execution_id,
            )
            if delayed and delayed.status in ("scheduled", "pending"):
                from app.models.workflow_delayed import DelayedExecutionStatus
                delayed.status = DelayedExecutionStatus.cancelled
                delayed.error = "Cart converted to order"

    if cancelled:
        await db.commit()
        logger.info(
            "Cancelled %d pending cart recovery executions for cart %s",
            cancelled, cart_id,
        )

    return cancelled


def _extract_phone_from_payload(payload: dict[str, Any]) -> str | None:
    """Try extracting phone from various Shopify payload locations."""
    # Try shipping address
    shipping = payload.get("shipping_address", {})
    if shipping and shipping.get("phone"):
        return shipping["phone"]

    # Try billing address
    billing = payload.get("billing_address", {})
    if billing and billing.get("phone"):
        return billing["phone"]

    # Try contact_email as fallback identifier
    return payload.get("phone")


def _extract_payment_method(payload: dict[str, Any]) -> str | None:
    """Extract payment method from Shopify order payload."""
    gateway = payload.get("gateway", "")
    if gateway:
        return gateway

    payment_details = payload.get("payment_details", {})
    if payment_details:
        return payment_details.get("credit_card_company", "")

    payment_methods = payload.get("payment_gateway_names", [])
    if payment_methods:
        return payment_methods[0]

    return None
