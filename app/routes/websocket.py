"""
WebSocket Route

Main WebSocket endpoint for real-time communication.
Handles authentication, room management, typing indicators, and presence.

Uses distributed connection manager with Redis pub/sub for multi-instance scalability.
"""

import json
import logging
import time

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.services.auth_service import decode_access_token
from app.services.redis_pubsub_manager import get_conversation_channel, get_workspace_channel
from app.services.websocket_manager import (
    emit_presence_update,
    emit_typing,
    get_distributed_manager,
)
from app.services.websocket_metrics import WebSocketEventType, WebSocketMetric, get_metrics_collector

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    Main WebSocket endpoint with multi-instance support.

    Authentication via JWT token in query parameter.

    Client events:
    - {"action": "join_conversation", "conversation_id": 123}
    - {"action": "leave_conversation", "conversation_id": 123}
    - {"action": "typing_start", "conversation_id": 123}
    - {"action": "typing_stop", "conversation_id": 123}
    - {"action": "ping"}

    Flow:
    1. Authenticate token
    2. Create distributed session
    3. Auto-join workspace room
    4. Process incoming messages
    5. Clean up on disconnect
    """
    session_id = None
    user_id = None
    workspace_id = None
    manager = get_distributed_manager()
    metrics = get_metrics_collector()

    # Authenticate
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        workspace_id = int(payload.get("workspace_id"))
    except Exception as exc:
        logger.error("WebSocket authentication failed: %s", exc)
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Connect and create session
    try:
        session_id = await manager.connect(websocket, user_id, workspace_id)
        logger.info(
            "WebSocket connection established: session=%s user=%d workspace=%d",
            session_id[:8],
            user_id,
            workspace_id,
        )

        # Emit presence update (online)
        await emit_presence_update(workspace_id, user_id, "online")

        # Main message loop
        while True:
            data = await websocket.receive_text()
            receive_time = time.time()

            try:
                message = json.loads(data)
                action = message.get("action", "")

                if action == "join_conversation":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        room = get_conversation_channel(conversation_id)
                        await manager.join_room(user_id, room, session_id)

                        await websocket.send_json({
                            "event_type": "room.joined",
                            "room": room,
                        })

                        await metrics.record_metric(
                            WebSocketMetric(
                                event_type=WebSocketEventType.room_joined,
                                workspace_id=workspace_id,
                                user_id=user_id,
                                session_id=session_id,
                                room=room,
                                latency_ms=int(
                                    (time.time() - receive_time) * 1000),
                            )
                        )

                elif action == "leave_conversation":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        room = get_conversation_channel(conversation_id)
                        await manager.leave_room(user_id, room)

                        await metrics.record_metric(
                            WebSocketMetric(
                                event_type=WebSocketEventType.room_left,
                                workspace_id=workspace_id,
                                user_id=user_id,
                                session_id=session_id,
                                room=room,
                            )
                        )

                elif action == "typing_start":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        await emit_typing(workspace_id, conversation_id, user_id, True)
                        await metrics.record_metric(
                            WebSocketMetric(
                                event_type=WebSocketEventType.typing_indicator,
                                workspace_id=workspace_id,
                                user_id=user_id,
                                session_id=session_id,
                            )
                        )

                elif action == "typing_stop":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        await emit_typing(workspace_id, conversation_id, user_id, False)

                elif action == "ping":
                    await websocket.send_json({"event_type": "pong"})

                else:
                    error_msg = f"Unknown action: {action}"
                    await websocket.send_json({
                        "event_type": "error",
                        "message": error_msg,
                    })

                    await metrics.record_metric(
                        WebSocketMetric(
                            event_type=WebSocketEventType.error_invalid_message,
                            workspace_id=workspace_id,
                            user_id=user_id,
                            session_id=session_id,
                            error_message=error_msg,
                        )
                    )

            except json.JSONDecodeError as exc:
                error_msg = "Invalid JSON"
                await websocket.send_json({
                    "event_type": "error",
                    "message": error_msg,
                })

                await metrics.record_metric(
                    WebSocketMetric(
                        event_type=WebSocketEventType.error_invalid_message,
                        workspace_id=workspace_id,
                        user_id=user_id,
                        session_id=session_id,
                        error_message=error_msg,
                    )
                )

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: user=%d", user_id)
    except Exception as exc:
        logger.error("WebSocket error user=%d: %s", user_id, exc)
        await metrics.record_metric(
            WebSocketMetric(
                event_type=WebSocketEventType.error_broadcast,
                workspace_id=workspace_id or 0,
                user_id=user_id,
                session_id=session_id,
                error_message=str(exc),
            )
        )
    finally:
        # Cleanup on disconnect
        if user_id:
            await manager.disconnect(user_id)
            if workspace_id:
                await emit_presence_update(workspace_id, user_id, "offline")

        logger.info("WebSocket session ended: session=%s user=%d",
                    session_id[:8] if session_id else "unknown", user_id or 0)
