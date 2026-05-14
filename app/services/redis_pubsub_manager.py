"""
Redis Pub/Sub Manager

Distributed WebSocket event broadcasting via Redis pub/sub.
Enables multi-instance scalability with cross-server message synchronization.

Architecture:
- workspace channels: ws:workspace:{workspace_id}
- conversation channels: ws:conversation:{conversation_id}
- presence channels: ws:presence:{workspace_id}
- user channels: ws:user:{user_id} for direct messages
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any, Callable

import aioredis
from redis import asyncio as aio_redis

logger = logging.getLogger(__name__)


class RedisPubSubManager:
    """
    Redis-backed pub/sub for distributed WebSocket messaging.

    Replaces in-memory room storage with Redis channels to support
    multi-instance deployment where different WebSocket connections
    may be on different servers.

    Channel Types:
    - Broadcast channels: ws:workspace:{id}, ws:conversation:{id}
    - Presence channels: ws:presence:{workspace_id}
    - Direct channels: ws:user:{user_id}
    - System channels: ws:system:* for cluster-wide events
    """

    def __init__(self, redis_url: str = "redis://localhost:6379/0"):
        self.redis_url = redis_url
        self.redis: aio_redis.Redis | None = None
        self.pubsub = None
        self._subscribers: dict[str, Callable] = {}
        self._lock = asyncio.Lock()

    async def initialize(self) -> None:
        """Initialize Redis connection."""
        try:
            self.redis = await aio_redis.from_url(self.redis_url, decode_responses=True)
            logger.info("Redis pub/sub manager initialized: %s",
                        self.redis_url)
        except Exception as exc:
            logger.error("Failed to initialize Redis: %s", exc)
            raise

    async def close(self) -> None:
        """Close Redis connection."""
        if self.redis:
            await self.redis.close()
            logger.info("Redis pub/sub manager closed")

    async def subscribe(
        self,
        channel: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> None:
        """
        Subscribe to a channel with a callback function.

        Callback receives deserialized JSON event.
        For async callbacks, use `asyncio.create_task()` or `await`.
        """
        async with self._lock:
            self._subscribers[channel] = callback

        logger.debug("Subscribed to channel: %s", channel)

    async def unsubscribe(self, channel: str) -> None:
        """Unsubscribe from a channel."""
        async with self._lock:
            self._subscribers.pop(channel, None)

        logger.debug("Unsubscribed from channel: %s", channel)

    async def publish(
        self,
        channel: str,
        event: dict[str, Any],
    ) -> None:
        """
        Publish an event to a Redis channel.

        Event is JSON-serialized for storage and deserialized on receive.
        """
        if not self.redis:
            logger.warning(
                "Redis not initialized, cannot publish to %s", channel)
            return

        try:
            message = json.dumps(event)
            await self.redis.publish(channel, message)
            logger.debug("Published to channel %s: event_type=%s",
                         channel, event.get("event_type"))
        except Exception as exc:
            logger.error("Failed to publish to %s: %s", channel, exc)

    async def message_listener(self) -> None:
        """
        Listen for Redis pub/sub messages and dispatch to subscribers.

        Runs in background task. Call with asyncio.create_task()
        """
        if not self.redis:
            logger.error("Redis not initialized")
            return

        pubsub = self.redis.pubsub()
        channels = list(self._subscribers.keys())

        if not channels:
            logger.info("No channels to subscribe to")
            return

        try:
            await pubsub.subscribe(*channels)
            logger.info("Started listening to %d channels", len(channels))

            async for message in pubsub.listen():
                if message["type"] == "message":
                    channel = message["channel"]
                    callback = self._subscribers.get(channel)

                    if callback:
                        try:
                            data = json.loads(message["data"])
                            # Support both sync and async callbacks
                            result = callback(data)
                            if asyncio.iscoroutine(result):
                                await result
                        except json.JSONDecodeError as exc:
                            logger.error(
                                "Invalid JSON from %s: %s", channel, exc)
                        except Exception as exc:
                            logger.error(
                                "Error in callback for %s: %s", channel, exc)

        except Exception as exc:
            logger.error("Message listener error: %s", exc)
        finally:
            await pubsub.close()

    async def get_channel_message_count(self, channel: str) -> int:
        """
        Get approximate number of subscribers to a channel.

        Useful for monitoring channel health.
        """
        if not self.redis:
            return 0

        try:
            # PUBSUB NUMSUB returns subscriber count
            result = await self.redis.execute_command("PUBSUB", "NUMSUB", channel)
            return result[1] if result else 0
        except Exception as exc:
            logger.warning(
                "Failed to get channel count for %s: %s", channel, exc)
            return 0

    async def set_session_data(
        self,
        session_key: str,
        data: dict[str, Any],
        ttl_seconds: int = 3600,
    ) -> None:
        """
        Store session data in Redis with TTL.

        session_key: Format like "session:{user_id}:{session_id}"
        """
        if not self.redis:
            logger.warning("Redis not initialized, cannot set session data")
            return

        try:
            serialized = json.dumps(data)
            await self.redis.setex(session_key, ttl_seconds, serialized)
            logger.debug("Session data stored: %s (ttl=%ds)",
                         session_key, ttl_seconds)
        except Exception as exc:
            logger.error("Failed to store session data %s: %s",
                         session_key, exc)

    async def get_session_data(self, session_key: str) -> dict[str, Any] | None:
        """Retrieve session data from Redis."""
        if not self.redis:
            return None

        try:
            data = await self.redis.get(session_key)
            if data:
                return json.loads(data)
        except Exception as exc:
            logger.error("Failed to get session data %s: %s", session_key, exc)

        return None

    async def delete_session_data(self, session_key: str) -> None:
        """Delete session data from Redis."""
        if not self.redis:
            return

        try:
            await self.redis.delete(session_key)
            logger.debug("Session data deleted: %s", session_key)
        except Exception as exc:
            logger.error("Failed to delete session data %s: %s",
                         session_key, exc)

    async def increment_presence_counter(
        self,
        presence_key: str,
        increment: int = 1,
        ttl_seconds: int = 300,
    ) -> int:
        """
        Increment a presence counter (for active user count).

        presence_key: Format like "presence:workspace:{workspace_id}"
        Returns: New counter value
        """
        if not self.redis:
            return 0

        try:
            value = await self.redis.incrby(presence_key, increment)
            await self.redis.expire(presence_key, ttl_seconds)
            return value
        except Exception as exc:
            logger.error("Failed to increment presence %s: %s",
                         presence_key, exc)
            return 0

    async def get_presence_counter(self, presence_key: str) -> int:
        """Get current presence counter value."""
        if not self.redis:
            return 0

        try:
            value = await self.redis.get(presence_key)
            return int(value) if value else 0
        except Exception as exc:
            logger.error("Failed to get presence %s: %s", presence_key, exc)
            return 0

    async def set_user_session(
        self,
        user_id: int,
        workspace_id: int,
        session_id: str,
        instance_id: str,
    ) -> None:
        """
        Record user session in Redis for multi-instance tracking.

        Stores which server instance has this user's WebSocket connection.
        """
        session_key = f"user_session:{user_id}"
        data = {
            "user_id": user_id,
            "workspace_id": workspace_id,
            "session_id": session_id,
            "instance_id": instance_id,
            "connected_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.set_session_data(session_key, data, ttl_seconds=7200)

    async def get_user_session(self, user_id: int) -> dict[str, Any] | None:
        """Get user session information."""
        session_key = f"user_session:{user_id}"
        return await self.get_session_data(session_key)

    async def clear_user_session(self, user_id: int) -> None:
        """Clear user session."""
        session_key = f"user_session:{user_id}"
        await self.delete_session_data(session_key)


# Global singleton instance
_redis_pubsub_manager: RedisPubSubManager | None = None


def get_redis_pubsub_manager() -> RedisPubSubManager:
    """Get or create global Redis pub/sub manager."""
    global _redis_pubsub_manager
    if _redis_pubsub_manager is None:
        _redis_pubsub_manager = RedisPubSubManager()
    return _redis_pubsub_manager


async def initialize_redis_pubsub(redis_url: str = "redis://localhost:6379/0") -> RedisPubSubManager:
    """Initialize and return Redis pub/sub manager."""
    manager = get_redis_pubsub_manager()
    manager.redis_url = redis_url
    await manager.initialize()
    return manager


# ──────────────────────────────────────────────────────────
# Channel Name Builders
# ──────────────────────────────────────────────────────────

def get_workspace_channel(workspace_id: int) -> str:
    """Channel for all workspace members."""
    return f"ws:workspace:{workspace_id}"


def get_conversation_channel(conversation_id: int) -> str:
    """Channel for conversation participants."""
    return f"ws:conversation:{conversation_id}"


def get_presence_channel(workspace_id: int) -> str:
    """Channel for workspace presence updates."""
    return f"ws:presence:{workspace_id}"


def get_user_channel(user_id: int) -> str:
    """Channel for direct user messages."""
    return f"ws:user:{user_id}"


def get_system_channel(channel_name: str) -> str:
    """System-wide channels for cluster coordination."""
    return f"ws:system:{channel_name}"


# ──────────────────────────────────────────────────────────
# Event Builders with Deduplication
# ──────────────────────────────────────────────────────────

def build_distributed_event(
    event_type: str,
    workspace_id: int,
    source_instance_id: str,
    source_session_id: str | None = None,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Build a WebSocket event with deduplication metadata.

    source_instance_id: Instance that generated this event
    source_session_id: Session that generated this event (for deduplication)
    """
    import uuid

    event_id = str(uuid.uuid4())

    return {
        "event_type": event_type,
        "workspace_id": workspace_id,
        "event_id": event_id,
        "source_instance_id": source_instance_id,
        "source_session_id": source_session_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }
