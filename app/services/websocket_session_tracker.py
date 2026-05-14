"""
WebSocket Session Tracker

Tracks WebSocket connections across multiple server instances.
Enables sticky-session independence and connection recovery.

Concepts:
- Session: Individual WebSocket connection
- Instance: Server hosting the connection
- Sticky session: Optional - connections can be rebalanced to any instance
"""

import asyncio
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from app.services.redis_pubsub_manager import get_redis_pubsub_manager

logger = logging.getLogger(__name__)


class WebSocketSession:
    """Represents a single WebSocket connection."""

    def __init__(
        self,
        session_id: str,
        user_id: int,
        workspace_id: int,
        instance_id: str,
    ):
        self.session_id = session_id
        self.user_id = user_id
        self.workspace_id = workspace_id
        self.instance_id = instance_id
        self.connected_at = datetime.now(timezone.utc)
        self.last_heartbeat = datetime.now(timezone.utc)
        self.rooms: set[str] = set()
        self.is_active = True

    def to_dict(self) -> dict[str, Any]:
        """Serialize session to dictionary."""
        return {
            "session_id": self.session_id,
            "user_id": self.user_id,
            "workspace_id": self.workspace_id,
            "instance_id": self.instance_id,
            "connected_at": self.connected_at.isoformat(),
            "last_heartbeat": self.last_heartbeat.isoformat(),
            "rooms": list(self.rooms),
            "is_active": self.is_active,
        }

    @staticmethod
    def from_dict(data: dict[str, Any]) -> "WebSocketSession":
        """Deserialize session from dictionary."""
        session = WebSocketSession(
            session_id=data["session_id"],
            user_id=data["user_id"],
            workspace_id=data["workspace_id"],
            instance_id=data["instance_id"],
        )
        session.connected_at = datetime.fromisoformat(data["connected_at"])
        session.last_heartbeat = datetime.fromisoformat(data["last_heartbeat"])
        session.rooms = set(data.get("rooms", []))
        session.is_active = data.get("is_active", True)
        return session


class WebSocketSessionTracker:
    """
    Tracks WebSocket sessions across instances.

    Local tracking for current instance connections.
    Redis storage for cluster-wide session coordination.
    """

    def __init__(self, instance_id: str | None = None):
        self.instance_id = instance_id or str(uuid.uuid4())
        # Local session storage: session_id → WebSocketSession
        self._local_sessions: dict[str, WebSocketSession] = {}
        self._lock = asyncio.Lock()
        self.redis_manager = get_redis_pubsub_manager()

    async def create_session(
        self,
        user_id: int,
        workspace_id: int,
    ) -> WebSocketSession:
        """
        Create and track a new WebSocket session.

        Returns session with unique session_id.
        """
        session_id = str(uuid.uuid4())
        session = WebSocketSession(
            session_id=session_id,
            user_id=user_id,
            workspace_id=workspace_id,
            instance_id=self.instance_id,
        )

        async with self._lock:
            self._local_sessions[session_id] = session

        # Store in Redis for cluster-wide visibility
        await self._store_session_in_redis(session)

        logger.info(
            "Session created: session_id=%s user=%d workspace=%d instance=%s",
            session_id,
            user_id,
            workspace_id,
            self.instance_id,
        )

        return session

    async def get_session(self, session_id: str) -> WebSocketSession | None:
        """Get session by ID (local first, then Redis)."""
        # Check local first
        async with self._lock:
            if session_id in self._local_sessions:
                return self._local_sessions[session_id]

        # Check Redis for remote sessions
        return await self._get_session_from_redis(session_id)

    async def get_user_sessions(self, user_id: int) -> list[WebSocketSession]:
        """
        Get all sessions for a user across all instances.

        Checks local and Redis storage.
        """
        sessions = []

        # Get local sessions
        async with self._lock:
            local = [s for s in self._local_sessions.values()
                     if s.user_id == user_id]
            sessions.extend(local)

        # Get from Redis (sessions on other instances)
        redis_sessions = await self._get_user_sessions_from_redis(user_id)
        sessions.extend(redis_sessions)

        return sessions

    async def get_workspace_sessions(self, workspace_id: int) -> list[WebSocketSession]:
        """
        Get all sessions in a workspace across all instances.

        Primarily for analytics/monitoring.
        """
        sessions = []

        # Get local sessions
        async with self._lock:
            local = [s for s in self._local_sessions.values(
            ) if s.workspace_id == workspace_id]
            sessions.extend(local)

        # Get from Redis (sessions on other instances)
        redis_sessions = await self._get_workspace_sessions_from_redis(workspace_id)
        sessions.extend(redis_sessions)

        return sessions

    async def update_session_heartbeat(self, session_id: str) -> None:
        """Update session last_heartbeat timestamp."""
        async with self._lock:
            if session_id in self._local_sessions:
                self._local_sessions[session_id].last_heartbeat = datetime.now(
                    timezone.utc)

    async def add_session_to_room(self, session_id: str, room: str) -> None:
        """Add session to a room."""
        async with self._lock:
            if session_id in self._local_sessions:
                self._local_sessions[session_id].rooms.add(room)

        # Update Redis
        session = await self.get_session(session_id)
        if session:
            await self._store_session_in_redis(session)

    async def remove_session_from_room(self, session_id: str, room: str) -> None:
        """Remove session from a room."""
        async with self._lock:
            if session_id in self._local_sessions:
                self._local_sessions[session_id].rooms.discard(room)

        # Update Redis
        session = await self.get_session(session_id)
        if session:
            await self._store_session_in_redis(session)

    async def close_session(self, session_id: str) -> None:
        """
        Mark session as closed and clean up.

        Removes from local storage and Redis.
        """
        async with self._lock:
            session = self._local_sessions.pop(session_id, None)

        if session:
            await self._delete_session_from_redis(session)
            logger.info("Session closed: session_id=%s user=%d",
                        session_id, session.user_id)

    async def get_stale_sessions(self, max_age_seconds: int = 300) -> list[WebSocketSession]:
        """
        Get sessions that haven't had activity in max_age_seconds.

        Useful for cleanup of disconnected sessions.
        """
        now = datetime.now(timezone.utc)
        stale = []

        async with self._lock:
            for session in self._local_sessions.values():
                age = (now - session.last_heartbeat).total_seconds()
                if age > max_age_seconds:
                    stale.append(session)

        return stale

    async def cleanup_stale_sessions(self, max_age_seconds: int = 300) -> int:
        """
        Close and remove stale sessions.

        Returns count of cleaned up sessions.
        """
        stale = await self.get_stale_sessions(max_age_seconds)
        count = 0

        for session in stale:
            await self.close_session(session.session_id)
            count += 1

        if count > 0:
            logger.info("Cleaned up %d stale sessions", count)

        return count

    # ──────────────────────────────────────────────────────────
    # Redis Persistence
    # ──────────────────────────────────────────────────────────

    async def _store_session_in_redis(self, session: WebSocketSession) -> None:
        """Store session in Redis for cluster-wide visibility."""
        try:
            session_key = f"ws_session:{session.session_id}"
            user_key = f"user_sessions:{session.user_id}"

            # Store session data
            await self.redis_manager.set_session_data(
                session_key,
                session.to_dict(),
                ttl_seconds=3600,
            )

            # Add to user's session set
            if self.redis_manager.redis:
                await self.redis_manager.redis.sadd(user_key, session.session_id)
                await self.redis_manager.redis.expire(user_key, 3600)

        except Exception as exc:
            logger.error("Failed to store session in Redis: %s", exc)

    async def _get_session_from_redis(self, session_id: str) -> WebSocketSession | None:
        """Retrieve session from Redis."""
        try:
            session_key = f"ws_session:{session_id}"
            data = await self.redis_manager.get_session_data(session_key)

            if data:
                return WebSocketSession.from_dict(data)
        except Exception as exc:
            logger.error("Failed to get session from Redis: %s", exc)

        return None

    async def _get_user_sessions_from_redis(self, user_id: int) -> list[WebSocketSession]:
        """Get all sessions for a user from Redis."""
        sessions = []
        try:
            user_key = f"user_sessions:{user_id}"
            if self.redis_manager.redis:
                session_ids = await self.redis_manager.redis.smembers(user_key)

                for session_id in session_ids:
                    session = await self._get_session_from_redis(session_id)
                    if session and session.instance_id != self.instance_id:
                        # Only include remote sessions
                        sessions.append(session)
        except Exception as exc:
            logger.error("Failed to get user sessions from Redis: %s", exc)

        return sessions

    async def _get_workspace_sessions_from_redis(self, workspace_id: int) -> list[WebSocketSession]:
        """Get all sessions in workspace from Redis."""
        sessions = []
        try:
            workspace_key = f"workspace_sessions:{workspace_id}"
            if self.redis_manager.redis:
                session_ids = await self.redis_manager.redis.smembers(workspace_key)

                for session_id in session_ids:
                    session = await self._get_session_from_redis(session_id)
                    if session and session.instance_id != self.instance_id:
                        # Only include remote sessions
                        sessions.append(session)
        except Exception as exc:
            logger.error(
                "Failed to get workspace sessions from Redis: %s", exc)

        return sessions

    async def _delete_session_from_redis(self, session: WebSocketSession) -> None:
        """Delete session from Redis."""
        try:
            session_key = f"ws_session:{session.session_id}"
            user_key = f"user_sessions:{session.user_id}"
            workspace_key = f"workspace_sessions:{session.workspace_id}"

            await self.redis_manager.delete_session_data(session_key)

            if self.redis_manager.redis:
                await self.redis_manager.redis.srem(user_key, session.session_id)
                await self.redis_manager.redis.srem(workspace_key, session.session_id)

        except Exception as exc:
            logger.error("Failed to delete session from Redis: %s", exc)


# Global instance tracker (one per server instance)
_session_tracker: WebSocketSessionTracker | None = None


def get_session_tracker(instance_id: str | None = None) -> WebSocketSessionTracker:
    """Get or create global session tracker."""
    global _session_tracker
    if _session_tracker is None:
        _session_tracker = WebSocketSessionTracker(instance_id)
    return _session_tracker
