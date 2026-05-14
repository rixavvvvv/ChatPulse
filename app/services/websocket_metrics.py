"""
WebSocket Metrics and Logging

Connection lifecycle tracking, event counters, and performance metrics.
Supports multi-instance monitoring with centralized Redis storage.

Metrics:
- Connection lifecycle: connects, disconnects, reconnects
- Event metrics: typing, presence, messages
- Performance: latency, broadcast count
- Errors: connection failures, event drops
"""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any

logger = logging.getLogger(__name__)


class WebSocketEventType(str, Enum):
    """WebSocket event types for metrics."""

    # Connection events
    connection_opened = "connection_opened"
    connection_closed = "connection_closed"
    connection_dropped = "connection_dropped"
    reconnection_attempt = "reconnection_attempt"
    reconnection_success = "reconnection_success"

    # Room events
    room_joined = "room_joined"
    room_left = "room_left"

    # Message events
    message_sent = "message_sent"
    message_received = "message_received"
    message_broadcast = "message_broadcast"

    # Presence events
    presence_update = "presence_update"
    typing_indicator = "typing_indicator"

    # Error events
    error_authentication = "error_authentication"
    error_broadcast = "error_broadcast"
    error_invalid_message = "error_invalid_message"

    # Distributed events
    cross_instance_message = "cross_instance_message"
    deduplication_skipped = "deduplication_skipped"


@dataclass
class WebSocketMetric:
    """Single WebSocket metric event."""

    event_type: WebSocketEventType
    workspace_id: int
    user_id: int | None = None
    session_id: str | None = None
    instance_id: str | None = None
    room: str | None = None
    error_message: str | None = None
    latency_ms: int | None = None
    broadcast_count: int | None = None
    timestamp: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert metric to dictionary."""
        return {
            "event_type": self.event_type.value,
            "workspace_id": self.workspace_id,
            "user_id": self.user_id,
            "session_id": self.session_id,
            "instance_id": self.instance_id,
            "room": self.room,
            "error_message": self.error_message,
            "latency_ms": self.latency_ms,
            "broadcast_count": self.broadcast_count,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class WebSocketMetrics:
    """Aggregated WebSocket metrics for a workspace."""

    workspace_id: int
    total_connections: int = 0
    total_disconnections: int = 0
    total_reconnections: int = 0
    active_connections: int = 0
    active_rooms: int = 0
    messages_sent: int = 0
    messages_received: int = 0
    broadcast_count: int = 0
    typing_indicators: int = 0
    presence_updates: int = 0
    errors_count: int = 0
    avg_latency_ms: float = 0.0
    instances_count: int = 0
    last_updated: datetime = field(
        default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert metrics to dictionary."""
        return {
            "workspace_id": self.workspace_id,
            "total_connections": self.total_connections,
            "total_disconnections": self.total_disconnections,
            "total_reconnections": self.total_reconnections,
            "active_connections": self.active_connections,
            "active_rooms": self.active_rooms,
            "messages_sent": self.messages_sent,
            "messages_received": self.messages_received,
            "broadcast_count": self.broadcast_count,
            "typing_indicators": self.typing_indicators,
            "presence_updates": self.presence_updates,
            "errors_count": self.errors_count,
            "avg_latency_ms": self.avg_latency_ms,
            "instances_count": self.instances_count,
            "last_updated": self.last_updated.isoformat(),
        }


class WebSocketMetricsCollector:
    """
    Collects and aggregates WebSocket metrics.

    Tracks per-workspace metrics and logs lifecycle events.
    """

    def __init__(self):
        # workspace_id → WebSocketMetrics
        self._metrics: dict[int, WebSocketMetrics] = {}
        # event_type → list of recent events (for analytics)
        self._recent_events: dict[WebSocketEventType,
                                  list[WebSocketMetric]] = {}
        self._lock = asyncio.Lock()
        # Keep last 1000 events per type for debugging
        self._max_recent_events = 1000

    async def record_metric(self, metric: WebSocketMetric) -> None:
        """Record a WebSocket metric event."""
        async with self._lock:
            # Get or create workspace metrics
            if metric.workspace_id not in self._metrics:
                self._metrics[metric.workspace_id] = WebSocketMetrics(
                    workspace_id=metric.workspace_id,
                )

            metrics = self._metrics[metric.workspace_id]

            # Update based on event type
            if metric.event_type == WebSocketEventType.connection_opened:
                metrics.total_connections += 1
                metrics.active_connections += 1

            elif metric.event_type == WebSocketEventType.connection_closed:
                metrics.total_disconnections += 1
                metrics.active_connections = max(
                    0, metrics.active_connections - 1)

            elif metric.event_type == WebSocketEventType.reconnection_success:
                metrics.total_reconnections += 1

            elif metric.event_type == WebSocketEventType.message_sent:
                metrics.messages_sent += 1

            elif metric.event_type == WebSocketEventType.message_received:
                metrics.messages_received += 1

            elif metric.event_type == WebSocketEventType.message_broadcast:
                metrics.broadcast_count += 1
                if metric.broadcast_count:
                    metrics.broadcast_count += metric.broadcast_count

            elif metric.event_type == WebSocketEventType.typing_indicator:
                metrics.typing_indicators += 1

            elif metric.event_type == WebSocketEventType.presence_update:
                metrics.presence_updates += 1

            elif metric.event_type in [
                WebSocketEventType.error_authentication,
                WebSocketEventType.error_broadcast,
                WebSocketEventType.error_invalid_message,
            ]:
                metrics.errors_count += 1

            # Update latency average
            if metric.latency_ms is not None:
                metrics.avg_latency_ms = (
                    metrics.avg_latency_ms + metric.latency_ms) / 2

            metrics.last_updated = datetime.now(timezone.utc)

            # Store recent event
            if metric.event_type not in self._recent_events:
                self._recent_events[metric.event_type] = []

            events = self._recent_events[metric.event_type]
            events.append(metric)

            # Keep only last N events
            if len(events) > self._max_recent_events:
                self._recent_events[metric.event_type] = events[-self._max_recent_events:]

        # Log event
        self._log_metric(metric)

    async def get_workspace_metrics(self, workspace_id: int) -> WebSocketMetrics | None:
        """Get metrics for a workspace."""
        async with self._lock:
            return self._metrics.get(workspace_id)

    async def get_all_metrics(self) -> dict[int, WebSocketMetrics]:
        """Get all workspace metrics."""
        async with self._lock:
            return dict(self._metrics)

    async def get_recent_events(
        self,
        event_type: WebSocketEventType | None = None,
        limit: int = 100,
    ) -> list[WebSocketMetric]:
        """Get recent events, optionally filtered by type."""
        async with self._lock:
            if event_type:
                events = self._recent_events.get(event_type, [])
                return events[-limit:]

            # Return recent events across all types
            all_events = []
            for events in self._recent_events.values():
                all_events.extend(events)

            # Sort by timestamp and return latest
            all_events.sort(key=lambda e: e.timestamp, reverse=True)
            return all_events[:limit]

    def _log_metric(self, metric: WebSocketMetric) -> None:
        """Log metric event to logger."""
        base_msg = f"WebSocket event: {metric.event_type.value}"

        if metric.user_id:
            base_msg += f" user={metric.user_id}"

        if metric.session_id:
            base_msg += f" session={metric.session_id[:8]}"

        if metric.room:
            base_msg += f" room={metric.room}"

        if metric.latency_ms is not None:
            base_msg += f" latency={metric.latency_ms}ms"

        if metric.broadcast_count is not None:
            base_msg += f" broadcast_count={metric.broadcast_count}"

        if metric.error_message:
            logger.warning(f"{base_msg} error={metric.error_message}")
        else:
            logger.debug(base_msg)


class WebSocketLifecycleLogger:
    """
    Detailed logging for WebSocket connection lifecycle.

    Logs connection establishment, room changes, disconnections, and errors.
    """

    def __init__(self):
        self.logger = logging.getLogger(__name__)

    async def log_connection_established(
        self,
        session_id: str,
        user_id: int,
        workspace_id: int,
        instance_id: str,
    ) -> None:
        """Log WebSocket connection establishment."""
        self.logger.info(
            "WebSocket connected: session=%s user=%d workspace=%d instance=%s",
            session_id[:8],
            user_id,
            workspace_id,
            instance_id[:8],
        )

    async def log_connection_closed(
        self,
        session_id: str,
        user_id: int,
        reason: str | None = None,
    ) -> None:
        """Log WebSocket disconnection."""
        msg = f"WebSocket disconnected: session={session_id[:8]} user={user_id}"
        if reason:
            msg += f" reason={reason}"

        self.logger.info(msg)

    async def log_room_joined(
        self,
        session_id: str,
        user_id: int,
        room: str,
    ) -> None:
        """Log user joining a room."""
        self.logger.debug(
            "Room joined: session=%s user=%d room=%s",
            session_id[:8],
            user_id,
            room,
        )

    async def log_room_left(
        self,
        session_id: str,
        user_id: int,
        room: str,
    ) -> None:
        """Log user leaving a room."""
        self.logger.debug(
            "Room left: session=%s user=%d room=%s",
            session_id[:8],
            user_id,
            room,
        )

    async def log_broadcast_sent(
        self,
        room: str,
        event_type: str,
        recipient_count: int,
        latency_ms: int,
    ) -> None:
        """Log broadcast event."""
        self.logger.debug(
            "Broadcast sent: room=%s event_type=%s recipients=%d latency=%dms",
            room,
            event_type,
            recipient_count,
            latency_ms,
        )

    async def log_message_received(
        self,
        session_id: str,
        user_id: int,
        action: str,
    ) -> None:
        """Log received message."""
        self.logger.debug(
            "Message received: session=%s user=%d action=%s",
            session_id[:8],
            user_id,
            action,
        )

    async def log_error(
        self,
        session_id: str,
        user_id: int | None,
        error_type: str,
        error_message: str,
    ) -> None:
        """Log error event."""
        self.logger.error(
            "WebSocket error: session=%s user=%s error_type=%s message=%s",
            session_id[:8] if session_id else "unknown",
            user_id or "unknown",
            error_type,
            error_message,
        )

    async def log_reconnection_attempt(
        self,
        user_id: int,
        session_id: str,
    ) -> None:
        """Log reconnection attempt."""
        self.logger.info(
            "Reconnection attempt: user=%d session=%s",
            user_id,
            session_id[:8],
        )

    async def log_distributed_message(
        self,
        event_id: str,
        source_instance: str,
        target_room: str,
    ) -> None:
        """Log distributed message across instances."""
        self.logger.debug(
            "Distributed message: event_id=%s source_instance=%s target_room=%s",
            event_id[:8],
            source_instance[:8],
            target_room,
        )

    async def log_deduplication_skipped(
        self,
        event_id: str,
        reason: str,
    ) -> None:
        """Log event deduplication."""
        self.logger.debug(
            "Deduplication skipped: event_id=%s reason=%s",
            event_id[:8],
            reason,
        )


# Global instances
_metrics_collector: WebSocketMetricsCollector | None = None
_lifecycle_logger: WebSocketLifecycleLogger | None = None


def get_metrics_collector() -> WebSocketMetricsCollector:
    """Get or create global metrics collector."""
    global _metrics_collector
    if _metrics_collector is None:
        _metrics_collector = WebSocketMetricsCollector()
    return _metrics_collector


def get_lifecycle_logger() -> WebSocketLifecycleLogger:
    """Get or create global lifecycle logger."""
    global _lifecycle_logger
    if _lifecycle_logger is None:
        _lifecycle_logger = WebSocketLifecycleLogger()
    return _lifecycle_logger
