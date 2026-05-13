"""
Conversation Tasks

Celery tasks for asynchronous conversation processing.
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.queue.base_tasks import FastIOTask

settings = get_settings()
logger = logging.getLogger(__name__)


class ProcessInboundMessageTask(FastIOTask):
    """
    Process an inbound message from a contact into the conversation system.

    Called from webhook processing when a new message is received from Meta.
    """

    name = "conversations.process_inbound"
    max_retries = 3

    def _do_execute(
        self,
        workspace_id: int,
        contact_id: int,
        content: str,
        content_type: str = "text",
        provider_message_id: str | None = None,
        metadata_json: dict | None = None,
    ) -> dict:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session_factory() as db:
                try:
                    from app.services import conversation_message_service

                    message, conversation = await conversation_message_service.create_inbound_message(
                        db=db,
                        workspace_id=workspace_id,
                        contact_id=contact_id,
                        content=content,
                        content_type=content_type,
                        provider_message_id=provider_message_id,
                        metadata_json=metadata_json or {},
                    )

                    # Emit WebSocket event
                    try:
                        from app.services.websocket_manager import emit_message_received
                        await emit_message_received(
                            workspace_id,
                            conversation.id,
                            {
                                "message_id": message.id,
                                "content": content,
                                "content_type": content_type,
                                "contact_id": contact_id,
                                "provider_message_id": provider_message_id,
                            },
                        )
                    except Exception as ws_exc:
                        logger.warning("WebSocket emit failed: %s", ws_exc)

                    return {
                        "status": "processed",
                        "conversation_id": conversation.id,
                        "message_id": message.id,
                        "created": True,
                    }

                except Exception as exc:
                    logger.error(
                        "Inbound message processing failed: workspace=%d contact=%d error=%s",
                        workspace_id, contact_id, exc,
                    )
                    raise

            await engine.dispose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


class ConversationCleanupTask(FastIOTask):
    """
    Periodic cleanup of stale conversations and expired agent presence.
    """

    name = "conversations.cleanup"
    max_retries = 1

    def _do_execute(self, workspace_id: int | None = None) -> dict:
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker

        engine = create_async_engine(settings.database_url, echo=False)
        async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async def _run():
            async with async_session_factory() as db:
                from app.services import agent_presence_service

                # Expire stale agent presence
                expired = await agent_presence_service.expire_stale_agents(db)

                return {
                    "status": "cleaned",
                    "expired_agents": expired,
                }

            await engine.dispose()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(_run())
        finally:
            loop.close()


def conversation_task_routes():
    return {
        "conversations.process_inbound": {"queue": "webhooks"},
        "conversations.cleanup": {"queue": "default"},
    }


process_inbound = ProcessInboundMessageTask()
conversation_cleanup = ConversationCleanupTask()
