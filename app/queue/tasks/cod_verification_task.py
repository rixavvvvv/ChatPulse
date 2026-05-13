"""
COD Verification Task

Processes COD (Cash on Delivery) orders with verification and reminder workflows.
Schedules verification messages and handles payment confirmation callbacks.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.queue.base_tasks import LongRunningTask

settings = get_settings()
logger = logging.getLogger(__name__)


class ProcessCodVerificationTask(LongRunningTask):
    """
    Process COD orders and manage verification workflow.

    Lifecycle:
    1. Order created with COD payment → trigger cod_pending
    2. Schedule verification message (e.g., 12h delay)
    3. If payment confirmed via webhook → cancel pending
    4. If not confirmed → send reminder
    5. After max reminders → mark as expired
    """

    name = "ecommerce.cod_verification"
    max_retries = 3

    def _do_execute(self, workspace_id: int, order_data: dict) -> dict:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session_factory() as db:
                try:
                    order_id = order_data.get("id")
                    phone = (
                        order_data.get("customer", {}).get("phone")
                        or order_data.get("shipping_address", {}).get("phone")
                    )

                    if not phone:
                        return {"status": "skipped", "reason": "no_phone"}

                    # Check if payment already confirmed
                    financial_status = order_data.get("financial_status", "").lower()
                    if financial_status in ("paid", "refunded"):
                        return {
                            "status": "skipped",
                            "reason": "already_paid",
                            "order_id": order_id,
                        }

                    # Process via orchestrator
                    from app.services.ecommerce_orchestrator_service import process_shopify_event

                    result = await process_shopify_event(
                        db=db,
                        workspace_id=workspace_id,
                        shopify_topic="orders/create",
                        payload=order_data,
                    )

                    return {
                        "status": "processed",
                        "order_id": order_id,
                        "payment_method": "cod",
                        "result": result,
                    }

                except Exception as exc:
                    logger.error(
                        "COD verification failed: workspace=%d order=%s error=%s",
                        workspace_id, order_data.get("id"), exc,
                    )
                    raise

            await engine.dispose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


class CodPaymentConfirmedTask(LongRunningTask):
    """
    Handle COD payment confirmation — cancel pending reminders.
    """

    name = "ecommerce.cod_payment_confirmed"
    max_retries = 2

    def _do_execute(self, workspace_id: int, order_id: str) -> dict:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session_factory() as db:
                from sqlalchemy import and_, select
                from app.models.ecommerce_automation import (
                    EcommerceAutomationExecution,
                    ExecutionStatus,
                )

                # Cancel pending COD verification executions
                stmt = select(EcommerceAutomationExecution).where(
                    and_(
                        EcommerceAutomationExecution.workspace_id == workspace_id,
                        EcommerceAutomationExecution.order_id == order_id,
                        EcommerceAutomationExecution.status.in_([
                            ExecutionStatus.pending,
                            ExecutionStatus.scheduled,
                        ]),
                    )
                )
                result = await db.execute(stmt)
                pending = list(result.scalars().all())

                cancelled = 0
                for execution in pending:
                    execution.status = ExecutionStatus.cancelled
                    execution.error = "Payment confirmed"
                    execution.updated_at = datetime.now(timezone.utc)
                    cancelled += 1

                await db.commit()

                return {
                    "status": "confirmed",
                    "order_id": order_id,
                    "cancelled_executions": cancelled,
                }

            await engine.dispose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


cod_verification = ProcessCodVerificationTask()
cod_payment_confirmed = CodPaymentConfirmedTask()
