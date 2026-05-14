"""
Celery tasks for ecommerce automation.

This module provides:
1. Order and cart event processing
2. Automation execution with delayed support
3. Attribution tracking
4. Metrics collection
"""

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.models.ecommerce_automation import (
    AttributionModel,
    AutomationTriggerType,
    EcommerceAutomationStatus,
    ExecutionStatus,
)
from app.queue.base_tasks import LongRunningTask

settings = get_settings()
logger = logging.getLogger(__name__)


def ecommerce_automation_routes():
    return {
        "ecommerce.process_order": {"queue": "ecommerce_automation"},
        "ecommerce.process_cart": {"queue": "ecommerce_automation"},
        "ecommerce.execute_automation": {"queue": "ecommerce_execution"},
        "ecommerce.track_shipment": {"queue": "ecommerce_automation"},
    }


class ProcessOrderTask(LongRunningTask):
    """
    Process order webhook and trigger relevant automations.
    """

    name = "ecommerce.process_order"
    max_retries = 3

    def _do_execute(self, workspace_id: int, order_data: dict) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                order_id = order_data.get("id")
                contact_id = order_data.get("contact_id")
                customer_phone = order_data.get("customer", {}).get("phone")

                automations = await self._get_triggered_automations(
                    db, workspace_id, AutomationTriggerType.order_created
                )

                executed = []
                skipped_duplicate = 0
                for automation in automations:
                    try:
                        from app.services import ecommerce_automation_service
                        from app.services.atomic_deduplication import generate_idempotency_key

                        # Generate idempotency key for atomic deduplication
                        idempotency_key = generate_idempotency_key(
                            "order", automation.id, str(order_id)
                        )

                        execution, created = await ecommerce_automation_service.create_execution(
                            db,
                            workspace_id=workspace_id,
                            automation_id=automation.id,
                            order_id=str(order_id),
                            cart_id=order_data.get("cart_id"),
                            contact_id=contact_id,
                            trigger_data=order_data,
                            idempotency_key=idempotency_key,
                        )

                        # Skip if already exists (atomic duplicate prevention)
                        if not created:
                            skipped_duplicate += 1
                            logger.info(
                                "Skipping duplicate execution for automation %d, order %s",
                                automation.id, order_id
                            )
                            continue

                        if automation.delay_seconds > 0:
                            delayed = await self._schedule_delayed_execution(
                                db, workspace_id, automation, execution, order_data
                            )
                            await ecommerce_automation_service.update_execution(
                                db, execution,
                                status=ExecutionStatus.scheduled,
                                delayed_execution_id=delayed.id,
                            )
                        else:
                            await self._execute_automation(db, automation, execution, order_data)

                        executed.append(automation.id)

                        if contact_id:
                            await self._track_attribution(
                                db, workspace_id, contact_id, str(order_id),
                                order_data.get("cart_id"), automation, execution.execution_id
                            )

                    except Exception as exc:
                        logger.error("Failed to execute automation %d for order %s: %s",
                                    automation.id, order_id, exc)

                await db.commit()
                return {
                    "status": "processed",
                    "order_id": order_id,
                    "automations_triggered": len(executed),
                    "executed_automation_ids": executed,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    async def _get_triggered_automations(self, db, workspace_id, trigger_type):
        from app.services import ecommerce_automation_service
        return await ecommerce_automation_service.get_pending_automations(
            db, trigger_type.value, workspace_id
        )

    async def _schedule_delayed_execution(self, db, workspace_id, automation, execution, order_data):
        from app.services import delayed_execution_service

        delayed = await delayed_execution_service.create_delayed_execution(
            db,
            workspace_id=workspace_id,
            workflow_definition_id=0,
            delay_type="fixed",
            delay_config={"duration_seconds": automation.delay_seconds},
            context={"execution_id": execution.execution_id, "automation_id": automation.id},
            trigger_data=order_data,
            max_retries=automation.max_retries,
        )
        return delayed

    async def _execute_automation(self, db, automation, execution, order_data):
        from app.services import ecommerce_automation_service, whatsapp_service

        action_config = automation.action_config
        template_id = action_config.get("template_id")

        message_payload = {
            "to": order_data.get("customer", {}).get("phone"),
            "template_id": template_id,
            "variables": order_data,
        }

        message_result = await whatsapp_service.send_template_message(
            workspace_id=automation.workspace_id,
            phone=order_data.get("customer", {}).get("phone"),
            template_id=template_id,
            variables=order_data,
        )

        await ecommerce_automation_service.update_execution(
            db, execution,
            status=ExecutionStatus.sent,
            message_id=message_result.get("message_id"),
            message_payload=message_payload,
            sent_at=datetime.now(timezone.utc),
        )

    async def _track_attribution(self, db, workspace_id, contact_id, order_id, cart_id, automation, execution_id):
        from app.services import ecommerce_automation_service

        touchpoints = [{
            "execution_id": execution_id,
            "type": "order_created",
            "automation_type": automation.automation_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }]

        await ecommerce_automation_service.create_attribution(
            db,
            workspace_id=workspace_id,
            contact_id=contact_id,
            order_id=order_id,
            cart_id=cart_id,
            attribution_model=AttributionModel.last_touch.value,
            touchpoints=touchpoints,
            revenue=0,
        )


class ProcessCartAbandonmentTask(LongRunningTask):
    """
    Process cart abandonment and trigger recovery automations.
    """

    name = "ecommerce.process_cart"
    max_retries = 3

    def _do_execute(self, workspace_id: int, cart_data: dict) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
        from datetime import timedelta

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                cart_id = cart_data.get("id")
                contact_id = cart_data.get("contact_id")
                customer_phone = cart_data.get("customer", {}).get("phone")

                automations = await self._get_abandoned_cart_automations(db, workspace_id)

                executed = []
                skipped_duplicate = 0
                for automation in automations:
                    try:
                        from app.services import ecommerce_automation_service
                        from app.services.atomic_deduplication import generate_idempotency_key

                        # Generate idempotency key for atomic deduplication
                        idempotency_key = generate_idempotency_key(
                            "cart", automation.id, str(cart_id)
                        )

                        execution, created = await ecommerce_automation_service.create_execution(
                            db,
                            workspace_id=workspace_id,
                            automation_id=automation.id,
                            cart_id=str(cart_id),
                            contact_id=contact_id,
                            trigger_data=cart_data,
                            idempotency_key=idempotency_key,
                        )

                        # Skip if already exists (atomic duplicate prevention)
                        if not created:
                            skipped_duplicate += 1
                            logger.info(
                                "Skipping duplicate cart recovery for automation %d, cart %s",
                                automation.id, cart_id
                            )
                            continue

                        trigger_config = automation.trigger_config.get("config", {})
                        cart_idle_minutes = trigger_config.get("cart_idle_minutes", 60)
                        delay_seconds = automation.delay_seconds or (cart_idle_minutes * 60)

                        if delay_seconds > 0:
                            delayed = await self._schedule_delayed_recovery(
                                db, workspace_id, automation, execution, cart_data, delay_seconds
                            )
                            await ecommerce_automation_service.update_execution(
                                db, execution,
                                status=ExecutionStatus.scheduled,
                                delayed_execution_id=delayed.id,
                            )
                        else:
                            await self._send_recovery_message(db, automation, execution, cart_data)

                        executed.append(automation.id)

                    except Exception as exc:
                        logger.error("Failed to process cart recovery %d: %s", automation.id, exc)

                await db.commit()
                return {
                    "status": "processed",
                    "cart_id": cart_id,
                    "recovery_automations_triggered": len(executed),
                    "duplicates_skipped": skipped_duplicate,
                }

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    async def _get_abandoned_cart_automations(self, db, workspace_id):
        from app.services import ecommerce_automation_service
        from app.models.ecommerce_automation import EcommerceAutomationType

        return await ecommerce_automation_service.get_pending_automations(
            db, AutomationTriggerType.cart_abandoned.value, workspace_id
        )

    async def _schedule_delayed_recovery(self, db, workspace_id, automation, execution, cart_data, delay_seconds):
        from app.services import delayed_execution_service

        delayed = await delayed_execution_service.create_delayed_execution(
            db,
            workspace_id=workspace_id,
            workflow_definition_id=0,
            delay_type="fixed",
            delay_config={"duration_seconds": delay_seconds},
            context={"execution_id": execution.execution_id, "automation_id": automation.id},
            trigger_data=cart_data,
            max_retries=automation.max_retries,
        )
        return delayed

    async def _send_recovery_message(self, db, automation, execution, cart_data):
        from app.services import ecommerce_automation_service, whatsapp_service

        action_config = automation.action_config
        template_id = action_config.get("template_id")

        message_payload = {
            "to": cart_data.get("customer", {}).get("phone"),
            "template_id": template_id,
            "variables": cart_data,
        }

        message_result = await whatsapp_service.send_template_message(
            workspace_id=automation.workspace_id,
            phone=cart_data.get("customer", {}).get("phone"),
            template_id=template_id,
            variables=cart_data,
        )

        await ecommerce_automation_service.update_execution(
            db, execution,
            status=ExecutionStatus.sent,
            message_id=message_result.get("message_id"),
            message_payload=message_payload,
            sent_at=datetime.now(timezone.utc),
        )


class ExecuteAutomationTask(LongRunningTask):
    """
    Execute a single automation with retry support.
    """

    name = "ecommerce.execute_automation"
    max_retries = 3

    def _do_execute(self, execution_id: str) -> dict:
        import asyncio
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session() as db:
                from app.services import ecommerce_automation_service

                execution = await ecommerce_automation_service.get_execution(db, execution_id, 0)
                if not execution:
                    return {"status": "execution_not_found"}

                automation = await ecommerce_automation_service.get_automation_by_id(
                    db, execution.automation_id, execution.workspace_id
                )

                if not automation or automation.status != EcommerceAutomationStatus.active:
                    await ecommerce_automation_service.update_execution(
                        db, execution,
                        status=ExecutionStatus.cancelled,
                        error="Automation not active",
                    )
                    return {"status": "automation_not_active"}

                try:
                    await self._send_message(db, automation, execution)
                    return {"status": "sent", "execution_id": execution_id}
                except Exception as exc:
                    if execution.retry_count < automation.max_retries:
                        await ecommerce_automation_service.update_execution(
                            db, execution,
                            retry_count=execution.retry_count + 1,
                        )
                        raise exc
                    else:
                        await ecommerce_automation_service.update_execution(
                            db, execution,
                            status=ExecutionStatus.failed,
                            error=str(exc),
                        )
                        return {"status": "failed", "error": str(exc)}

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    async def _send_message(self, db, automation, execution):
        from app.services import ecommerce_automation_service, whatsapp_service

        action_config = automation.action_config
        template_id = action_config.get("template_id")
        trigger_data = execution.trigger_data

        message_result = await whatsapp_service.send_template_message(
            workspace_id=automation.workspace_id,
            phone=trigger_data.get("customer", {}).get("phone"),
            template_id=template_id,
            variables=trigger_data,
        )

        await ecommerce_automation_service.update_execution(
            db, execution,
            status=ExecutionStatus.sent,
            message_id=message_result.get("message_id"),
            sent_at=datetime.now(timezone.utc),
        )


process_order = ProcessOrderTask()
process_cart = ProcessCartAbandonmentTask()
execute_automation = ExecuteAutomationTask()