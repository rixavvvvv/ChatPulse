"""
Shipment Tracking Task

Processes fulfillment webhooks from Shopify and triggers
shipment_updates and delivered_notifications automations.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.queue.base_tasks import LongRunningTask

settings = get_settings()
logger = logging.getLogger(__name__)


class ProcessShipmentTask(LongRunningTask):
    """
    Process Shopify fulfillment webhooks and trigger shipment automations.

    Handles:
    - fulfillments/create → shipment_created trigger
    - fulfillments/update → shipment_delivered trigger (if status is delivered)
    """

    name = "ecommerce.track_shipment"
    max_retries = 3

    def _do_execute(self, workspace_id: int, fulfillment_data: dict) -> dict:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session_factory() as db:
                try:
                    from app.services.ecommerce_orchestrator_service import process_shopify_event

                    # Determine the Shopify topic from fulfillment data
                    status = fulfillment_data.get("shipment_status", "").lower()
                    topic = "fulfillments/update" if status == "delivered" else "fulfillments/create"

                    # Enrich fulfillment data
                    enriched = self._enrich_fulfillment_data(fulfillment_data)

                    result = await process_shopify_event(
                        db=db,
                        workspace_id=workspace_id,
                        shopify_topic=topic,
                        payload=enriched,
                    )

                    return {
                        "status": "processed",
                        "fulfillment_id": fulfillment_data.get("id"),
                        "order_id": fulfillment_data.get("order_id"),
                        "shipment_status": status,
                        "result": result,
                    }

                except Exception as exc:
                    logger.error(
                        "Shipment tracking failed: workspace=%d fulfillment=%s error=%s",
                        workspace_id, fulfillment_data.get("id"), exc,
                    )
                    raise

            await engine.dispose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()

    def _enrich_fulfillment_data(self, data: dict) -> dict:
        """Enrich fulfillment data with normalized fields."""
        enriched = dict(data)

        # Normalize tracking info
        tracking = data.get("tracking_info", {})
        if not tracking:
            tracking = {
                "number": data.get("tracking_number"),
                "url": data.get("tracking_url"),
                "company": data.get("tracking_company"),
            }
        enriched["tracking_info"] = tracking

        # Normalize carrier
        enriched["carrier"] = (
            data.get("tracking_company")
            or tracking.get("company")
            or "Unknown"
        )

        # Normalize tracking URL
        enriched["tracking_url"] = (
            data.get("tracking_url")
            or tracking.get("url")
            or ""
        )

        # Map line items
        line_items = data.get("line_items", [])
        enriched["item_count"] = len(line_items)
        enriched["item_summary"] = ", ".join(
            item.get("name", "Item") for item in line_items[:3]
        )
        if len(line_items) > 3:
            enriched["item_summary"] += f" +{len(line_items) - 3} more"

        return enriched


process_shipment = ProcessShipmentTask()
