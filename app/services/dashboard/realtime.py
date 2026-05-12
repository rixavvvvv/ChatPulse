"""
Real-time pub/sub infrastructure for dashboard updates.

Provides:
- Redis pub/sub for real-time metric broadcasts
- Room-based subscriptions (workspace, campaign)
- SSE endpoint support
- Event streaming helpers
- Channel management
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Any, AsyncGenerator

import redis.asyncio as redis

from app.core.config import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()


# ─────────────────────────────────────────────────────────────────────────────
# Channel Definitions
# ─────────────────────────────────────────────────────────────────────────────


class Channel(str, Enum):
    """Pub/sub channel names."""

    WORKSPACE_PREFIX = "chatpulse:ws"
    CAMPAIGN_PREFIX = "chatpulse:campaign"
    QUEUE = "chatpulse:queue"
    SYSTEM = "chatpulse:system"

    @classmethod
    def workspace(cls, workspace_id: int) -> str:
        """Get workspace-specific channel."""
        return f"{cls.WORKSPACE_PREFIX}:{workspace_id}"

    @classmethod
    def campaign(cls, campaign_id: int) -> str:
        """Get campaign-specific channel."""
        return f"{cls.CAMPAIGN_PREFIX}:{campaign_id}"

    @classmethod
    def workspace_pattern(cls) -> str:
        """Get pattern for all workspace channels."""
        return f"{cls.WORKSPACE_PREFIX}:*"

    @classmethod
    def campaign_pattern(cls) -> str:
        """Get pattern for all campaign channels."""
        return f"{cls.CAMPAIGN_PREFIX}:*"


# ─────────────────────────────────────────────────────────────────────────────
# Message Types
# ─────────────────────────────────────────────────────────────────────────────


class EventKind(str, Enum):
    """Event kinds for real-time updates."""

    METRIC_UPDATE = "metric.update"
    CAMPAIGN_PROGRESS = "campaign.progress"
    QUEUE_STATUS = "queue.status"
    ALERT = "alert"
    HEARTBEAT = "heartbeat"
    WORKSPACE_UPDATE = "workspace.update"


class RealtimeMessage:
    """Real-time message wrapper."""

    def __init__(
        self,
        kind: EventKind,
        workspace_id: int,
        data: dict[str, Any],
        channel: str | None = None,
        campaign_id: int | None = None,
        trace_id: str | None = None,
    ):
        self.kind = kind
        self.workspace_id = workspace_id
        self.campaign_id = campaign_id
        self.channel = channel
        self.trace_id = trace_id or _generate_trace_id()
        self.timestamp = datetime.now(timezone.utc)
        self.data = data

    def to_json(self) -> str:
        """Serialize to JSON string."""
        return json.dumps({
            "kind": self.kind.value,
            "workspace_id": self.workspace_id,
            "campaign_id": self.campaign_id,
            "channel": self.channel,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        })

    @classmethod
    def from_json(cls, raw: str) -> RealtimeMessage:
        """Deserialize from JSON string."""
        obj = json.loads(raw)
        return cls(
            kind=EventKind(obj["kind"]),
            workspace_id=obj["workspace_id"],
            campaign_id=obj.get("campaign_id"),
            channel=obj.get("channel"),
            trace_id=obj.get("trace_id"),
            data=obj["data"],
        )


# ─────────────────────────────────────────────────────────────────────────────
# Pub/Sub Service
# ─────────────────────────────────────────────────────────────────────────────


class RealtimePubSubService:
    """
    Redis-based pub/sub service for real-time dashboard updates.

    Features:
    - Workspace-scoped broadcasts
    - Campaign-scoped broadcasts
    - System-wide announcements
    - Connection management
    - Reconnection support
    """

    def __init__(self, redis_url: str | None = None):
        self._redis_url = redis_url or settings.redis_url
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._subscriptions: dict[str, set[AsyncGenerator]] = {}
        self._lock = asyncio.Lock()

    async def _get_redis(self) -> redis.Redis:
        """Get or create Redis connection."""
        if self._redis is None:
            self._redis = redis.from_url(
                self._redis_url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._redis

    async def close(self) -> None:
        """Close all connections."""
        if self._pubsub:
            await self._pubsub.close()
            self._pubsub = None
        if self._redis:
            await self._redis.close()
            self._redis = None

    # ─────────────────────────────────────────────────────────────────────────
    # Publishing
    # ─────────────────────────────────────────────────────────────────────────

    async def publish(
        self,
        channel: str,
        message: RealtimeMessage | dict[str, Any],
        to_workspace: int | None = None,
        to_campaign: int | None = None,
    ) -> int:
        """
        Publish a message to a channel.

        Returns number of subscribers that received the message.
        """
        r = await self._get_redis()

        if isinstance(message, dict):
            payload = json.dumps(message)
        else:
            payload = message.to_json()

        count = await r.publish(channel, payload)
        logger.debug(f"Published to {channel}: {count} subscribers")
        return count

    async def publish_workspace(
        self,
        workspace_id: int,
        kind: EventKind,
        data: dict[str, Any],
    ) -> int:
        """Publish to workspace channel."""
        channel = Channel.workspace(workspace_id)
        message = RealtimeMessage(
            kind=kind,
            workspace_id=workspace_id,
            data=data,
            channel=channel,
        )
        return await self.publish(channel, message)

    async def publish_campaign(
        self,
        workspace_id: int,
        campaign_id: int,
        kind: EventKind,
        data: dict[str, Any],
    ) -> int:
        """Publish to campaign channel."""
        channel = Channel.campaign(campaign_id)
        message = RealtimeMessage(
            kind=kind,
            workspace_id=workspace_id,
            campaign_id=campaign_id,
            data=data,
            channel=channel,
        )
        # Also publish to workspace channel
        await self.publish(Channel.workspace(workspace_id), message)
        return await self.publish(channel, message)

    async def publish_metric_update(
        self,
        workspace_id: int,
        metric_name: str,
        value: Any,
        campaign_id: int | None = None,
    ) -> int:
        """Publish a metric update."""
        data = {
            "metric": metric_name,
            "value": value,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return await self.publish_workspace(
            workspace_id,
            EventKind.METRIC_UPDATE,
            data,
        )

    async def publish_campaign_progress(
        self,
        workspace_id: int,
        campaign_id: int,
        sent: int,
        delivered: int,
        failed: int,
        total: int,
    ) -> int:
        """Publish campaign progress update."""
        progress_percent = round((sent / total * 100) if total > 0 else 0, 1)
        data = {
            "campaign_id": campaign_id,
            "sent": sent,
            "delivered": delivered,
            "failed": failed,
            "total": total,
            "progress_percent": progress_percent,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        return await self.publish_campaign(
            workspace_id,
            campaign_id,
            EventKind.CAMPAIGN_PROGRESS,
            data,
        )

    async def publish_alert(
        self,
        workspace_id: int,
        alert_id: str,
        severity: str,
        message: str,
        metric_name: str,
        current_value: float,
        threshold: float,
    ) -> int:
        """Publish an alert."""
        data = {
            "alert_id": alert_id,
            "severity": severity,
            "message": message,
            "metric_name": metric_name,
            "current_value": current_value,
            "threshold": threshold,
            "created_at": datetime.now(timezone.utc).isoformat(),
        }
        return await self.publish_workspace(
            workspace_id,
            EventKind.ALERT,
            data,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Subscribing
    # ─────────────────────────────────────────────────────────────────────────

    async def subscribe(
        self,
        channels: str | list[str],
    ) -> AsyncGenerator[RealtimeMessage, None]:
        """
        Subscribe to channels and yield messages.

        Usage:
            async for msg in pubsub.subscribe("chatpulse:ws:1"):
                print(msg.kind, msg.data)
        """
        if isinstance(channels, str):
            channels = [channels]

        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(*channels)

        try:
            async for raw in pubsub.listen():
                if raw["type"] == "message":
                    try:
                        msg = RealtimeMessage.from_json(raw["data"])
                        yield msg
                    except Exception as exc:
                        logger.warning(f"Failed to parse message: {exc}")
        finally:
            await pubsub.unsubscribe(*channels)
            await pubsub.close()

    async def subscribe_workspace(
        self,
        workspace_id: int,
    ) -> AsyncGenerator[RealtimeMessage, None]:
        """Subscribe to workspace channel."""
        channel = Channel.workspace(workspace_id)
        async for msg in self.subscribe(channel):
            yield msg

    async def subscribe_campaign(
        self,
        campaign_id: int,
    ) -> AsyncGenerator[RealtimeMessage, None]:
        """Subscribe to campaign channel."""
        channel = Channel.campaign(campaign_id)
        async for msg in self.subscribe(channel):
            yield msg

    # ─────────────────────────────────────────────────────────────────────────
    # SSE Helpers
    # ─────────────────────────────────────────────────────────────────────────

    async def sse_stream(
        self,
        workspace_id: int,
        heartbeat_interval: int = 30,
    ) -> AsyncGenerator[str, None]:
        """
        Generate SSE-formatted stream for a workspace.

        Yields properly formatted SSE data strings.
        """
        channel = Channel.workspace(workspace_id)
        r = await self._get_redis()
        pubsub = r.pubsub()
        await pubsub.subscribe(channel)

        try:
            last_heartbeat = datetime.now(timezone.utc)

            async for raw in pubsub.listen():
                if raw["type"] == "message":
                    try:
                        msg = RealtimeMessage.from_json(raw["data"])
                        yield f"event: {msg.kind.value}\ndata: {raw['data']}\n\n"
                    except Exception as exc:
                        logger.warning(f"Failed to parse SSE message: {exc}")

                # Send heartbeat
                now = datetime.now(timezone.utc)
                if (now - last_heartbeat).total_seconds() >= heartbeat_interval:
                    yield f"event: heartbeat\ndata: {json.dumps({'timestamp': now.isoformat()})}\n\n"
                    last_heartbeat = now

        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    # ─────────────────────────────────────────────────────────────────────────
    # Connection Stats
    # ─────────────────────────────────────────────────────────────────────────

    async def get_active_channels(self) -> dict[str, int]:
        """Get count of subscribers per channel."""
        r = await self._get_redis()
        pattern = "chatpulse:*"
        channels: dict[str, int] = {}
        cursor = 0

        while True:
            cursor, keys = await r.pubsub_channels(cursor=cursor, pattern=pattern)
            for key in keys:
                count = await r.pubsub_numsub(key)
                channels[key] = count[0][1] if count else 0
            if cursor == 0:
                break

        return channels

    async def get_channel_subscribers(self, channel: str) -> int:
        """Get number of subscribers for a channel."""
        r = await self._get_redis()
        result = await r.pubsub_numsub(channel)
        return result[0][1] if result else 0


# ─────────────────────────────────────────────────────────────────────────────
# Utility
# ─────────────────────────────────────────────────────────────────────────────


def _generate_trace_id() -> str:
    """Generate a trace ID for message correlation."""
    import uuid
    return str(uuid.uuid4())[:12]


# ─────────────────────────────────────────────────────────────────────────────
# Singleton
# ─────────────────────────────────────────────────────────────────────────────

_realtime_service: RealtimePubSubService | None = None


def get_realtime_service() -> RealtimePubSubService:
    """Get singleton realtime service instance."""
    global _realtime_service
    if _realtime_service is None:
        _realtime_service = RealtimePubSubService()
    return _realtime_service
