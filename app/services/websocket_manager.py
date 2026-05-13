"""
WebSocket Manager

Connection management, room-based broadcasting, typing indicators, and presence events.
Uses FastAPI's built-in WebSocket support.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Any

from fastapi import WebSocket, WebSocketDisconnect

logger = logging.getLogger(__name__)


class ConnectionManager:
    """
    Manages WebSocket connections with room-based broadcasting.

    Rooms:
    - workspace:{workspace_id} — all agents in a workspace
    - conversation:{conversation_id} — agents viewing a specific conversation
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

        logger.info("WebSocket connected: user=%d workspace=%d", user_id, workspace_id)

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


# Global singleton instance
manager = ConnectionManager()


# ──────────────────────────────────────────────────────────
# Event Builders
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


async def emit_conversation_created(workspace_id: int, conversation_data: dict) -> None:
    event = build_event("conversation.created", workspace_id, conversation_data)
    await manager.broadcast_to_workspace(workspace_id, event)


async def emit_conversation_updated(workspace_id: int, conversation_data: dict) -> None:
    event = build_event("conversation.updated", workspace_id, conversation_data)
    await manager.broadcast_to_workspace(workspace_id, event)


async def emit_conversation_assigned(
    workspace_id: int,
    conversation_id: int,
    assignment_data: dict,
) -> None:
    event = build_event("conversation.assigned", workspace_id, {
        "conversation_id": conversation_id,
        **assignment_data,
    })
    await manager.broadcast_to_workspace(workspace_id, event)


async def emit_message_received(
    workspace_id: int,
    conversation_id: int,
    message_data: dict,
) -> None:
    event = build_event("message.received", workspace_id, {
        "conversation_id": conversation_id,
        **message_data,
    })
    # Broadcast to workspace (for inbox list) and conversation (for chat view)
    await manager.broadcast_to_workspace(workspace_id, event)


async def emit_message_sent(
    workspace_id: int,
    conversation_id: int,
    message_data: dict,
    sender_user_id: int,
) -> None:
    event = build_event("message.sent", workspace_id, {
        "conversation_id": conversation_id,
        **message_data,
    })
    await manager.broadcast_to_workspace(workspace_id, event, exclude_user_id=sender_user_id)


async def emit_typing(
    workspace_id: int,
    conversation_id: int,
    user_id: int,
    is_typing: bool,
) -> None:
    event = build_event("typing", workspace_id, {
        "conversation_id": conversation_id,
        "user_id": user_id,
        "is_typing": is_typing,
    })
    await manager.broadcast_to_conversation(
        conversation_id, event, exclude_user_id=user_id
    )


async def emit_presence_update(
    workspace_id: int,
    user_id: int,
    status: str,
) -> None:
    event = build_event("presence.update", workspace_id, {
        "user_id": user_id,
        "status": status,
    })
    await manager.broadcast_to_workspace(workspace_id, event, exclude_user_id=user_id)


async def emit_unread_update(
    user_id: int,
    workspace_id: int,
    conversation_id: int,
    unread_count: int,
) -> None:
    event = build_event("unread.update", workspace_id, {
        "conversation_id": conversation_id,
        "unread_count": unread_count,
    })
    await manager.send_to_user(user_id, event)
