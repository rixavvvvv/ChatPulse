"""
WebSocket Route

Main WebSocket endpoint for real-time communication.
Handles authentication, room management, typing indicators, and presence.
"""

import json
import logging

from fastapi import APIRouter, Depends, Query, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.services.auth_service import decode_access_token
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

router = APIRouter(tags=["websocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
):
    """
    Main WebSocket endpoint.

    Authentication via JWT token in query parameter.

    Client events:
    - {"action": "join_conversation", "conversation_id": 123}
    - {"action": "leave_conversation", "conversation_id": 123}
    - {"action": "typing_start", "conversation_id": 123}
    - {"action": "typing_stop", "conversation_id": 123}
    - {"action": "ping"}
    """
    # Authenticate
    try:
        payload = decode_access_token(token)
        user_id = int(payload.get("sub"))
        workspace_id = int(payload.get("workspace_id"))
    except Exception:
        await websocket.close(code=4001, reason="Authentication failed")
        return

    # Connect
    await manager.connect(websocket, user_id, workspace_id)

    # Emit presence update
    from app.services.websocket_manager import emit_presence_update
    await emit_presence_update(workspace_id, user_id, "online")

    try:
        while True:
            data = await websocket.receive_text()

            try:
                message = json.loads(data)
                action = message.get("action", "")

                if action == "join_conversation":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        await manager.join_room(
                            user_id, f"conversation:{conversation_id}"
                        )
                        await websocket.send_json({
                            "event_type": "room.joined",
                            "room": f"conversation:{conversation_id}",
                        })

                elif action == "leave_conversation":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        await manager.leave_room(
                            user_id, f"conversation:{conversation_id}"
                        )

                elif action == "typing_start":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        from app.services.websocket_manager import emit_typing
                        await emit_typing(workspace_id, conversation_id, user_id, True)

                elif action == "typing_stop":
                    conversation_id = message.get("conversation_id")
                    if conversation_id:
                        from app.services.websocket_manager import emit_typing
                        await emit_typing(workspace_id, conversation_id, user_id, False)

                elif action == "ping":
                    await websocket.send_json({"event_type": "pong"})

                else:
                    await websocket.send_json({
                        "event_type": "error",
                        "message": f"Unknown action: {action}",
                    })

            except json.JSONDecodeError:
                await websocket.send_json({
                    "event_type": "error",
                    "message": "Invalid JSON",
                })

    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.error("WebSocket error user=%d: %s", user_id, exc)
    finally:
        await manager.disconnect(user_id)
        await emit_presence_update(workspace_id, user_id, "offline")
