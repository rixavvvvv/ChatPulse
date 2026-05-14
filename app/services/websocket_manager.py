"""
WebSocket Manager

Connection management, room-based broadcasting, typing indicators, and presence events.

Architecture:
- DistributedConnectionManager: Multi-instance with Redis pub/sub
- Local connection tracking for current server
- Redis pub/sub for cross-instance messaging
- Deduplication of events across instances
- Session tracking for reconnection safety
"""

import asyncio
import json
import logging
import time
import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from fastapi import WebSocket, WebSocketDisconnect

from app.services.redis_pubsub_manager import (
    build_distributed_event,
    get_conversation_channel,
    get_presence_channel,
    get_redis_pubsub_manager,
    get_user_channel,
    get_workspace_channel,
)
from app.services.websocket_metrics import (
    WebSocketEventType,
    WebSocketLifecycleLogger,
    WebSocketMetric,
    get_lifecycle_logger,
    get_metrics_collector,
)
from app.services.websocket_session_tracker import get_session_tracker

logger = logging.getLogger(__name__)


class DistributedConnectionManager:
    """
    Multi-instance WebSocket connection manager with Redis pub/sub.

    Features:
    - Sticky session independence (connections can rebalance)
    - Distributed room membership tracking
    - Cross-instance broadcasting via Redis
    - Deduplication of events
    - Connection lifecycle logging
    - Metrics collection

    Rooms:
    - workspace:{workspace_id} — all agents in a workspace
    - conversation:{conversation_id} — agents viewing a conversation
    """

    def __init__(self, instance_id: str | None = None):
        self.instance_id = instance_id or str(uuid.uuid4())
        # Local connections: user_id → WebSocket
        self._connections: dict[int, WebSocket] = {}
        # Local room memberships: user_id → set of rooms
        self._user_rooms: dict[int, set[str]] = {}
        # Session tracking
        self._session_tracker = get_session_tracker(self.instance_id)
        # Redis pub/sub
        self._redis_manager = get_redis_pubsub_manager()
        # Metrics and logging
        self._metrics = get_metrics_collector()
        self._lifecycle_logger = get_lifecycle_logger()
        # Deduplication: event_id → timestamp (to prevent duplicate broadcasts)
        self._processed_events: dict[str, float] = {}
        self._dedup_max_age = 60  # seconds
        self._lock = asyncio.Lock()

        logger.info(
            "DistributedConnectionManager initialized: instance_id=%s", self.instance_id[:8])

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        workspace_id: int,
    ) -> str:
        """
        Accept WebSocket connection and create session.

        Returns session_id for tracking.
        """
        await websocket.accept()

        # Create session
        session = await self._session_tracker.create_session(user_id, workspace_id)

        async with self._lock:
            # Close existing connection for same user (only 1 per user)
            if user_id in self._connections:
                try:
                    await self._connections[user_id].close()
                except Exception:
                    pass

            self._connections[user_id] = websocket
            self._user_rooms[user_id] = set()

        # Log connection
        await self._lifecycle_logger.log_connection_established(
            session.session_id, user_id, workspace_id, self.instance_id
        )

        # Record metric
        await self._metrics.record_metric(
            WebSocketMetric(
                event_type=WebSocketEventType.connection_opened,
                workspace_id=workspace_id,
                user_id=user_id,
                session_id=session.session_id,
                instance_id=self.instance_id,
            )
        )

        # Auto-join workspace room
        await self.join_room(user_id, get_workspace_channel(workspace_id), session.session_id)

        return session.session_id

    async def disconnect(self, user_id: int, reason: str | None = None) -> None:
        """Remove user from all rooms and clean up connection."""
        session = None

        async with self._lock:
            # Get user's rooms before cleanup
            rooms = self._user_rooms.pop(user_id, set())

            # Leave all rooms locally
            for room in rooms:
                await self._session_tracker.remove_session_from_room(
                    list(self._local_sessions_for_user(user_id))[0]
                    if self._local_sessions_for_user(user_id)
                    else None,
                    room,
                )

            # Remove connection
            self._connections.pop(user_id, None)

        # Clean up session
        sessions = await self._session_tracker.get_user_sessions(user_id)
        if sessions:
            session = sessions[0]
            await self._session_tracker.close_session(session.session_id)

        # Log disconnection
        if session:
            await self._lifecycle_logger.log_connection_closed(session.session_id, user_id, reason)

            # Record metric
            await self._metrics.record_metric(
                WebSocketMetric(
                    event_type=WebSocketEventType.connection_closed,
                    workspace_id=session.workspace_id,
                    user_id=user_id,
                    session_id=session.session_id,
                    instance_id=self.instance_id,
                )
            )

    async def join_room(self, user_id: int, room: str, session_id: str | None = None) -> None:
        """Add user to a room for targeted broadcasts."""
        async with self._lock:
            if user_id not in self._user_rooms:
                self._user_rooms[user_id] = set()
            self._user_rooms[user_id].add(room)

        # Update session tracking
        if session_id:
            await self._session_tracker.add_session_to_room(session_id, room)

        # Log
        if session_id:
            sessions = await self._session_tracker.get_user_sessions(user_id)
            if sessions:
                await self._lifecycle_logger.log_room_joined(session_id, user_id, room)

    async def leave_room(self, user_id: int, room: str) -> None:
        """Remove user from a room."""
        async with self._lock:
            if user_id in self._user_rooms:
                self._user_rooms[user_id].discard(room)

        # Update session tracking
        sessions = await self._session_tracker.get_user_sessions(user_id)
        if sessions:
            await self._session_tracker.remove_session_from_room(sessions[0].session_id, room)
            await self._lifecycle_logger.log_room_left(sessions[0].session_id, user_id, room)

    async def send_to_user(self, user_id: int, event: dict[str, Any]) -> bool:
        """Send event directly to user on this instance."""
        ws = self._connections.get(user_id)
        if ws:
            try:
                await ws.send_json(event)
                return True
            except Exception as exc:
                logger.warning("Failed to send to user %d: %s", user_id, exc)
                await self.disconnect(user_id, reason="send_failed")
        return False

    async def broadcast_to_room(
        self,
        room: str,
        event: dict[str, Any],
        exclude_user_id: int | None = None,
    ) -> int:
        """
        Broadcast event to all users in a room (this instance only).

        For cross-instance broadcasting, use publish_to_room_redis.
        """
        sent = 0

        async with self._lock:
            # Find users in this room on this instance
            users_in_room = [
                uid for uid, rooms in self._user_rooms.items()
                if room in rooms and uid != exclude_user_id
            ]

        for user_id in users_in_room:
            if await self.send_to_user(user_id, event):
                sent += 1

        return sent

    async def broadcast_to_workspace(
        self,
        workspace_id: int,
        event: dict[str, Any],
        exclude_user_id: int | None = None,
    ) -> int:
        """Broadcast to all users in a workspace (local only)."""
        return await self.broadcast_to_room(
            get_workspace_channel(workspace_id),
            event,
            exclude_user_id,
        )

    async def broadcast_to_conversation(
        self,
        conversation_id: int,
        event: dict[str, Any],
        exclude_user_id: int | None = None,
    ) -> int:
        """Broadcast to all users in a conversation (local only)."""
        return await self.broadcast_to_room(
            get_conversation_channel(conversation_id),
            event,
            exclude_user_id,
        )

    async def publish_to_room_redis(
        self,
        room: str,
        event: dict[str, Any],
        exclude_session_id: str | None = None,
    ) -> None:
        """
        Publish event to Redis channel for multi-instance broadcasting.

        Event will be delivered to all instances, which will distribute
        locally to their connected clients.
        """
        # Add deduplication info
        if "source_instance_id" not in event:
            event["source_instance_id"] = self.instance_id
        if "source_session_id" not in event:
            event["source_session_id"] = exclude_session_id

        await self._redis_manager.publish(room, event)

        logger.debug("Published to Redis: room=%s event_type=%s",
                     room, event.get("event_type"))

    async def register_redis_listener(
        self,
        room: str,
        callback: Callable[[dict[str, Any]], Any],
    ) -> None:
        """Register callback for Redis channel."""
        await self._redis_manager.subscribe(room, callback)
        logger.debug("Registered Redis listener for room: %s", room)

    def _local_sessions_for_user(self, user_id: int) -> list[str]:
        """Get session IDs for user on this instance."""
        # Placeholder - in real implementation, track session_id → user_id
        return []

    def get_connected_users(self, workspace_id: int | None = None) -> list[int]:
        """Get list of connected user IDs on this instance."""
        if workspace_id:
            return [
                uid for uid, rooms in self._user_rooms.items()
                if get_workspace_channel(workspace_id) in rooms
            ]
        return list(self._connections.keys())

    def get_room_members(self, room: str) -> set[int]:
        """Get user IDs in a room on this instance."""
        return {
            uid for uid, rooms in self._user_rooms.items()
            if room in rooms
        }

    @property
    def active_connections(self) -> int:
        """Number of active connections on this instance."""
        return len(self._connections)

    async def _clean_old_dedup_events(self) -> None:
        """Clean up old event IDs from deduplication cache."""
        now = time.time()
        expired = [
            eid for eid, ts in self._processed_events.items()
            if now - ts > self._dedup_max_age
        ]

        for eid in expired:
            self._processed_events.pop(eid, None)

    async def _check_duplicate(self, event_id: str) -> bool:
        """
        Check if event has already been processed (deduplication).

        Returns True if duplicate, False if new.
        """
        if event_id in self._processed_events:
            await self._metrics.record_metric(
                WebSocketMetric(
                    event_type=WebSocketEventType.deduplication_skipped,
                    workspace_id=0,
                    error_message="Duplicate event ID",
                )
            )
            return True

        self._processed_events[event_id] = time.time()

        # Periodically clean old entries
        if len(self._processed_events) > 10000:
            await self._clean_old_dedup_events()

        return False


# Legacy in-memory manager for backward compatibility
class ConnectionManager:
    """
    In-memory connection manager (legacy).

    Kept for backward compatibility. New code should use DistributedConnectionManager.
    """

    def __init__(self):
        # user_id → WebSocket connection
        self._connections: dict[int, WebSocket] = {}
        # user_id → set of room names
        self._user_rooms: dict[int, set[str]] = {}
        # room_name → set of user_ids
        self._room_members: dict[str, set[int]] = {}
        # user_id → workspace_id
        self._user_workspace: dict[int, int] = {}
        self._lock = asyncio.Lock()

    async def connect(
        self,
        websocket: WebSocket,
        user_id: int,
        workspace_id: int,
    ) -> None:
        """Accept WebSocket connection and join workspace room."""
        await websocket.accept()

        async with self._lock:
            # Disconnect existing connection for same user (only 1 connection per user)
            if user_id in self._connections:
                try:
                    await self._connections[user_id].close()
                except Exception:
                    pass

            self._connections[user_id] = websocket
            self._user_rooms[user_id] = set()
            self._user_workspace[user_id] = workspace_id

        # Auto-join workspace room
        await self.join_room(user_id, f"workspace:{workspace_id}")

        logger.info("WebSocket connected: user=%d workspace=%d",
                    user_id, workspace_id)

    async def disconnect(self, user_id: int) -> None:
        """Remove user from all rooms and clean up connection."""
        async with self._lock:
            # Leave all rooms
            rooms = self._user_rooms.pop(user_id, set())
            for room in rooms:
                if room in self._room_members:
                    self._room_members[room].discard(user_id)
                    if not self._room_members[room]:
                        del self._room_members[room]

            self._connections.pop(user_id, None)
            self._user_workspace.pop(user_id, None)

        logger.info("WebSocket disconnected: user=%d", user_id)

    async def join_room(self, user_id: int, room: str) -> None:
        """Add user to a room for targeted broadcasts."""
        async with self._lock:
            if user_id not in self._user_rooms:
                self._user_rooms[user_id] = set()
            self._user_rooms[user_id].add(room)

            if room not in self._room_members:
                self._room_members[room] = set()
            self._room_members[room].add(user_id)

    async def leave_room(self, user_id: int, room: str) -> None:
        """Remove user from a room."""
        async with self._lock:
            if user_id in self._user_rooms:
                self._user_rooms[user_id].discard(room)
            if room in self._room_members:
                self._room_members[room].discard(user_id)
                if not self._room_members[room]:
                    del self._room_members[room]

    async def send_to_user(self, user_id: int, event: dict[str, Any]) -> bool:
        """Send event directly to a specific user."""
        ws = self._connections.get(user_id)
        if ws:
            try:
                await ws.send_json(event)
                return True
            except Exception as exc:
                logger.warning("Failed to send to user %d: %s", user_id, exc)
                await self.disconnect(user_id)
        return False

    async def broadcast_to_room(
        self,
        room: str,
        event: dict[str, Any],
        exclude_user_id: int | None = None,
    ) -> int:
        """Broadcast event to all users in a room. Returns count of recipients."""
        members = self._room_members.get(room, set()).copy()
        sent = 0

        for user_id in members:
            if user_id == exclude_user_id:
                continue
            if await self.send_to_user(user_id, event):
                sent += 1

        return sent

    async def broadcast_to_workspace(
        self,
        workspace_id: int,
        event: dict[str, Any],
        exclude_user_id: int | None = None,
    ) -> int:
        """Broadcast to all users in a workspace."""
        return await self.broadcast_to_room(
            f"workspace:{workspace_id}",
            event,
            exclude_user_id,
        )

    async def broadcast_to_conversation(
        self,
        conversation_id: int,
        event: dict[str, Any],
        exclude_user_id: int | None = None,
    ) -> int:
        """Broadcast to all users viewing a conversation."""
        return await self.broadcast_to_room(
            f"conversation:{conversation_id}",
            event,
            exclude_user_id,
        )

    def get_connected_users(self, workspace_id: int | None = None) -> list[int]:
        """Get list of connected user IDs."""
        if workspace_id:
            return [
                uid for uid, wid in self._user_workspace.items()
                if wid == workspace_id
            ]
        return list(self._connections.keys())

    def get_room_members(self, room: str) -> set[int]:
        """Get user IDs in a room."""
        return self._room_members.get(room, set()).copy()

    @property
    def active_connections(self) -> int:
        return len(self._connections)


# Global singleton instances
manager = ConnectionManager()  # Legacy in-memory manager
distributed_manager: DistributedConnectionManager | None = None


def get_distributed_manager() -> DistributedConnectionManager:
    """Get or create global distributed connection manager."""
    global distributed_manager
    if distributed_manager is None:
        distributed_manager = DistributedConnectionManager()
    return distributed_manager


async def initialize_distributed_manager(
    instance_id: str | None = None,
    redis_url: str = "redis://localhost:6379/0",
) -> DistributedConnectionManager:
    """Initialize distributed manager with Redis pub/sub."""
    redis_manager = get_redis_pubsub_manager()
    redis_manager.redis_url = redis_url
    await redis_manager.initialize()

    global distributed_manager
    distributed_manager = DistributedConnectionManager(instance_id)
    return distributed_manager


# ──────────────────────────────────────────────────────────
# Event Builders (Legacy - In-Memory)
# ──────────────────────────────────────────────────────────

def build_event(
    event_type: str,
    workspace_id: int,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a standard WebSocket event."""
    return {
        "event_type": event_type,
        "workspace_id": workspace_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "payload": payload or {},
    }


# ──────────────────────────────────────────────────────────
# Distributed Event Builders (with Redis pub/sub)
# ──────────────────────────────────────────────────────────

async def emit_conversation_created(workspace_id: int, conversation_data: dict) -> None:
    """Emit conversation created event across all instances."""
    dm = get_distributed_manager()
    event = build_distributed_event(
        "conversation.created",
        workspace_id,
        dm.instance_id,
        payload=conversation_data,
    )
    await dm.publish_to_room_redis(get_workspace_channel(workspace_id), event)
    # Also broadcast locally
    await dm.broadcast_to_workspace(workspace_id, event)


async def emit_conversation_updated(workspace_id: int, conversation_data: dict) -> None:
    """Emit conversation updated event across all instances."""
    dm = get_distributed_manager()
    event = build_distributed_event(
        "conversation.updated",
        workspace_id,
        dm.instance_id,
        payload=conversation_data,
    )
    await dm.publish_to_room_redis(get_workspace_channel(workspace_id), event)
    await dm.broadcast_to_workspace(workspace_id, event)


async def emit_conversation_assigned(
    workspace_id: int,
    conversation_id: int,
    assignment_data: dict,
) -> None:
    """Emit conversation assigned event across all instances."""
    dm = get_distributed_manager()
    payload = {
        "conversation_id": conversation_id,
        **assignment_data,
    }
    event = build_distributed_event(
        "conversation.assigned",
        workspace_id,
        dm.instance_id,
        payload=payload,
    )
    await dm.publish_to_room_redis(get_workspace_channel(workspace_id), event)
    await dm.broadcast_to_workspace(workspace_id, event)


async def emit_message_received(
    workspace_id: int,
    conversation_id: int,
    message_data: dict,
) -> None:
    """Emit message received event across all instances."""
    dm = get_distributed_manager()
    payload = {
        "conversation_id": conversation_id,
        **message_data,
    }
    event = build_distributed_event(
        "message.received",
        workspace_id,
        dm.instance_id,
        payload=payload,
    )
    # Publish to both workspace and conversation channels
    await dm.publish_to_room_redis(get_workspace_channel(workspace_id), event)
    await dm.publish_to_room_redis(get_conversation_channel(conversation_id), event)


async def emit_message_sent(
    workspace_id: int,
    conversation_id: int,
    message_data: dict,
    sender_user_id: int,
) -> None:
    """Emit message sent event across all instances (excluding sender)."""
    dm = get_distributed_manager()
    payload = {
        "conversation_id": conversation_id,
        **message_data,
    }
    event = build_distributed_event(
        "message.sent",
        workspace_id,
        dm.instance_id,
        payload=payload,
    )
    await dm.publish_to_room_redis(get_workspace_channel(workspace_id), event)
    # Don't send back to sender
    await dm.broadcast_to_workspace(workspace_id, event, exclude_user_id=sender_user_id)


async def emit_typing(
    workspace_id: int,
    conversation_id: int,
    user_id: int,
    is_typing: bool,
) -> None:
    """Emit typing indicator across all instances."""
    dm = get_distributed_manager()
    event = build_distributed_event(
        "typing",
        workspace_id,
        dm.instance_id,
        payload={
            "conversation_id": conversation_id,
            "user_id": user_id,
            "is_typing": is_typing,
        },
    )
    await dm.publish_to_room_redis(
        get_conversation_channel(conversation_id),
        event,
    )
    await dm.broadcast_to_conversation(conversation_id, event, exclude_user_id=user_id)


async def emit_presence_update(
    workspace_id: int,
    user_id: int,
    status: str,
) -> None:
    """Emit presence update across all instances."""
    dm = get_distributed_manager()
    event = build_distributed_event(
        "presence.update",
        workspace_id,
        dm.instance_id,
        payload={
            "user_id": user_id,
            "status": status,
        },
    )
    await dm.publish_to_room_redis(get_presence_channel(workspace_id), event)
    await dm.broadcast_to_workspace(workspace_id, event, exclude_user_id=user_id)


async def emit_unread_update(
    user_id: int,
    workspace_id: int,
    conversation_id: int,
    unread_count: int,
) -> None:
    """Emit unread update to specific user (no distribution needed)."""
    dm = get_distributed_manager()
    event = build_distributed_event(
        "unread.update",
        workspace_id,
        dm.instance_id,
        payload={
            "conversation_id": conversation_id,
            "unread_count": unread_count,
        },
    )
    await dm.send_to_user(user_id, event)
