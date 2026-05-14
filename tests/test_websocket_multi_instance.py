"""
Tests for multi-instance WebSocket infrastructure.

Covers:
- Redis pub/sub publishing and subscription
- Session creation and tracking
- Cross-instance message delivery
- Deduplication of events
- Connection lifecycle
- Room membership management
"""

import asyncio
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.redis_pubsub_manager import (
    RedisPubSubManager,
    build_distributed_event,
    get_conversation_channel,
    get_presence_channel,
    get_user_channel,
    get_workspace_channel,
)
from app.services.websocket_session_tracker import (
    WebSocketSession,
    WebSocketSessionTracker,
)
from app.services.websocket_metrics import (
    WebSocketEventType,
    WebSocketMetric,
    WebSocketMetricsCollector,
    WebSocketLifecycleLogger,
)


class TestRedisPubSubManager:
    """Test Redis pub/sub manager."""

    @pytest.mark.asyncio
    async def test_build_distributed_event(self):
        """Test event building with deduplication metadata."""
        event = build_distributed_event(
            "typing",
            workspace_id=10,
            source_instance_id="instance-1",
            source_session_id="session-abc",
            payload={"user_id": 42, "is_typing": True},
        )

        assert event["event_type"] == "typing"
        assert event["workspace_id"] == 10
        assert event["source_instance_id"] == "instance-1"
        assert event["source_session_id"] == "session-abc"
        assert event["payload"]["user_id"] == 42
        assert "event_id" in event
        assert "timestamp" in event

    @pytest.mark.asyncio
    async def test_channel_name_builders(self):
        """Test Redis channel name generation."""
        assert get_workspace_channel(10) == "ws:workspace:10"
        assert get_conversation_channel(100) == "ws:conversation:100"
        assert get_presence_channel(10) == "ws:presence:10"
        assert get_user_channel(42) == "ws:user:42"

    @pytest.mark.asyncio
    async def test_session_data_storage(self):
        """Test Redis session data persistence."""
        manager = RedisPubSubManager()

        # Mock Redis
        manager.redis = AsyncMock()
        manager.redis.setex = AsyncMock()
        manager.redis.get = AsyncMock(return_value='{"key": "value"}')

        # Store
        await manager.set_session_data("session:123", {"key": "value"}, ttl_seconds=3600)
        manager.redis.setex.assert_called_once()

        # Retrieve
        data = await manager.get_session_data("session:123")
        assert data == {"key": "value"}

    @pytest.mark.asyncio
    async def test_deduplication_event_tracking(self):
        """Test deduplication event cache."""
        manager = RedisPubSubManager()

        event_id = "evt-123"

        # First occurrence: not a duplicate
        is_dup = await manager._check_duplicate(event_id)
        assert is_dup is False

        # Second occurrence: is a duplicate
        is_dup = await manager._check_duplicate(event_id)
        assert is_dup is True


class TestWebSocketSessionTracker:
    """Test WebSocket session tracking."""

    @pytest.mark.asyncio
    async def test_create_session(self):
        """Test session creation."""
        tracker = WebSocketSessionTracker(instance_id="instance-1")

        # Mock Redis manager
        tracker.redis_manager.set_session_data = AsyncMock()

        # Create session
        session = await tracker.create_session(user_id=42, workspace_id=10)

        assert session.session_id is not None
        assert session.user_id == 42
        assert session.workspace_id == 10
        assert session.instance_id == "instance-1"
        assert session.is_active is True

    @pytest.mark.asyncio
    async def test_session_serialization(self):
        """Test session to/from dict."""
        session = WebSocketSession(
            session_id="sess-123",
            user_id=42,
            workspace_id=10,
            instance_id="instance-1",
        )
        session.rooms.add("ws:workspace:10")

        # Serialize
        data = session.to_dict()
        assert data["session_id"] == "sess-123"
        assert data["user_id"] == 42
        assert "ws:workspace:10" in data["rooms"]

        # Deserialize
        restored = WebSocketSession.from_dict(data)
        assert restored.session_id == "sess-123"
        assert restored.user_id == 42
        assert "ws:workspace:10" in restored.rooms

    @pytest.mark.asyncio
    async def test_get_user_sessions_cross_instance(self):
        """Test getting sessions for user across instances."""
        tracker = WebSocketSessionTracker(instance_id="instance-1")
        tracker.redis_manager.redis = AsyncMock()

        # Mock: User has session on instance-2
        remote_session_data = {
            "session_id": "sess-remote",
            "user_id": 42,
            "workspace_id": 10,
            "instance_id": "instance-2",
            "connected_at": "2024-05-14T10:00:00Z",
            "last_heartbeat": "2024-05-14T10:00:00Z",
            "rooms": [],
            "is_active": True,
        }
        tracker.redis_manager.get_session_data = AsyncMock(
            return_value=remote_session_data)
        tracker.redis_manager.redis.smembers = AsyncMock(
            return_value={"sess-remote"})

        # Get sessions (should include remote)
        sessions = await tracker.get_user_sessions(user_id=42)
        assert len(sessions) > 0

    @pytest.mark.asyncio
    async def test_stale_session_cleanup(self):
        """Test cleanup of stale sessions."""
        tracker = WebSocketSessionTracker(instance_id="instance-1")
        tracker.redis_manager.delete_session_data = AsyncMock()

        # Create old session (older than max_age)
        import datetime
        session = WebSocketSession("sess-old", 42, 10, "instance-1")
        session.last_heartbeat = datetime.datetime.now(
            datetime.timezone.utc) - datetime.timedelta(seconds=400)

        # Add to local storage
        tracker._local_sessions["sess-old"] = session

        # Cleanup (max_age=300 seconds)
        count = await tracker.cleanup_stale_sessions(max_age_seconds=300)
        assert count == 1


class TestWebSocketMetrics:
    """Test WebSocket metrics collection."""

    @pytest.mark.asyncio
    async def test_record_connection_metric(self):
        """Test recording connection metrics."""
        collector = WebSocketMetricsCollector()

        metric = WebSocketMetric(
            event_type=WebSocketEventType.connection_opened,
            workspace_id=10,
            user_id=42,
            session_id="sess-123",
            instance_id="instance-1",
        )

        await collector.record_metric(metric)

        # Check workspace metrics updated
        metrics = await collector.get_workspace_metrics(workspace_id=10)
        assert metrics is not None
        assert metrics.total_connections == 1
        assert metrics.active_connections == 1

    @pytest.mark.asyncio
    async def test_metrics_aggregation(self):
        """Test metrics aggregation across events."""
        collector = WebSocketMetricsCollector()

        # Record various metrics
        await collector.record_metric(WebSocketMetric(
            event_type=WebSocketEventType.connection_opened,
            workspace_id=10,
            user_id=42,
        ))
        await collector.record_metric(WebSocketMetric(
            event_type=WebSocketEventType.message_sent,
            workspace_id=10,
            user_id=42,
        ))
        await collector.record_metric(WebSocketMetric(
            event_type=WebSocketEventType.connection_closed,
            workspace_id=10,
            user_id=42,
        ))

        metrics = await collector.get_workspace_metrics(workspace_id=10)
        assert metrics.total_connections == 1
        assert metrics.total_disconnections == 1
        assert metrics.messages_sent == 1

    @pytest.mark.asyncio
    async def test_recent_events_tracking(self):
        """Test tracking of recent events."""
        collector = WebSocketMetricsCollector()

        # Record events
        for i in range(5):
            await collector.record_metric(WebSocketMetric(
                event_type=WebSocketEventType.typing_indicator,
                workspace_id=10,
                user_id=42 + i,
            ))

        # Get recent events
        recent = await collector.get_recent_events(
            event_type=WebSocketEventType.typing_indicator,
            limit=10,
        )
        assert len(recent) == 5

    @pytest.mark.asyncio
    async def test_lifecycle_logger(self):
        """Test lifecycle logging."""
        logger = WebSocketLifecycleLogger()

        # These should log without errors
        await logger.log_connection_established(
            session_id="sess-123",
            user_id=42,
            workspace_id=10,
            instance_id="instance-1",
        )

        await logger.log_connection_closed(
            session_id="sess-123",
            user_id=42,
            reason="client_disconnect",
        )

        await logger.log_room_joined(
            session_id="sess-123",
            user_id=42,
            room="ws:conversation:100",
        )

        await logger.log_error(
            session_id="sess-123",
            user_id=42,
            error_type="send_failed",
            error_message="WebSocket.send() failed",
        )


class TestDistributedConnectionManager:
    """Test distributed connection manager."""

    @pytest.mark.asyncio
    async def test_duplicate_event_detection(self):
        """Test deduplication of events."""
        from app.services.websocket_manager import DistributedConnectionManager

        manager = DistributedConnectionManager(instance_id="instance-1")

        event_id = "evt-123"

        # First check: not a duplicate
        result = await manager._check_duplicate(event_id)
        assert result is False

        # Second check: is a duplicate
        result = await manager._check_duplicate(event_id)
        assert result is True

    @pytest.mark.asyncio
    async def test_dedup_cache_cleanup(self):
        """Test deduplication cache cleanup."""
        from app.services.websocket_manager import DistributedConnectionManager

        manager = DistributedConnectionManager(instance_id="instance-1")
        manager._dedup_max_age = 1  # 1 second

        # Add events
        import time
        for i in range(5):
            manager._processed_events[f"evt-{i}"] = time.time()

        # Wait for TTL
        await asyncio.sleep(1.1)

        # Cleanup
        await manager._clean_old_dedup_events()

        # Cache should be empty
        assert len(manager._processed_events) == 0


class TestCrossInstanceScenarios:
    """Test cross-instance messaging scenarios."""

    @pytest.mark.asyncio
    async def test_typing_indicator_broadcast(self):
        """Test typing indicator propagation across instances."""
        # Scenario: User A on Instance 1 types, User B on Instance 2 receives

        from app.services.websocket_manager import emit_typing

        # Mock the distributed manager
        with patch("app.services.websocket_manager.get_distributed_manager") as mock_manager:
            instance = AsyncMock()
            instance.instance_id = "instance-1"
            instance.publish_to_room_redis = AsyncMock()
            instance.broadcast_to_conversation = AsyncMock()
            mock_manager.return_value = instance

            # Emit typing
            await emit_typing(
                workspace_id=10,
                conversation_id=100,
                user_id=42,
                is_typing=True,
            )

            # Verify it was published to Redis
            instance.publish_to_room_redis.assert_called_once()

    @pytest.mark.asyncio
    async def test_presence_sync_across_instances(self):
        """Test presence updates synchronized across instances."""
        from app.services.websocket_manager import emit_presence_update

        with patch("app.services.websocket_manager.get_distributed_manager") as mock_manager:
            instance = AsyncMock()
            instance.instance_id = "instance-1"
            instance.publish_to_room_redis = AsyncMock()
            instance.broadcast_to_workspace = AsyncMock()
            mock_manager.return_value = instance

            # Emit presence change
            await emit_presence_update(
                workspace_id=10,
                user_id=42,
                status="online",
            )

            # Verify published to presence channel
            instance.publish_to_room_redis.assert_called_once()
            call_args = instance.publish_to_room_redis.call_args
            assert "ws:presence:10" in str(call_args)

    @pytest.mark.asyncio
    async def test_message_delivery_all_instances(self):
        """Test message delivered to users on all instances."""
        from app.services.websocket_manager import emit_message_sent

        with patch("app.services.websocket_manager.get_distributed_manager") as mock_manager:
            instance = AsyncMock()
            instance.instance_id = "instance-1"
            instance.publish_to_room_redis = AsyncMock()
            instance.broadcast_to_workspace = AsyncMock()
            mock_manager.return_value = instance

            # Emit message
            await emit_message_sent(
                workspace_id=10,
                conversation_id=100,
                message_data={"content": "Hello"},
                sender_user_id=42,
            )

            # Verify published to workspace channel (for all instances to receive)
            assert instance.publish_to_room_redis.called


class TestReconnectionScenarios:
    """Test reconnection across instances."""

    @pytest.mark.asyncio
    async def test_reconnect_to_different_instance(self):
        """Test user reconnecting to different instance."""
        tracker1 = WebSocketSessionTracker(instance_id="instance-1")
        tracker2 = WebSocketSessionTracker(instance_id="instance-2")

        # Mock Redis
        tracker1.redis_manager.redis = AsyncMock()
        tracker2.redis_manager.redis = AsyncMock()
        tracker1.redis_manager.set_session_data = AsyncMock()
        tracker1.redis_manager.get_session_data = AsyncMock()

        # Create session on instance-1
        session1 = await tracker1.create_session(user_id=42, workspace_id=10)
        await tracker1.add_session_to_room(session1.session_id, "ws:conversation:100")

        # Simulate reconnect on instance-2
        sessions = await tracker2.get_user_sessions(user_id=42)
        # In real scenario, would look up previous session and restore membership

        # Create new session on instance-2
        session2 = await tracker2.create_session(user_id=42, workspace_id=10)
        await tracker2.add_session_to_room(session2.session_id, "ws:conversation:100")

        # Both sessions should exist in Redis
        assert session1.session_id is not None
        assert session2.session_id is not None
        assert session1.instance_id == "instance-1"
        assert session2.instance_id == "instance-2"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
