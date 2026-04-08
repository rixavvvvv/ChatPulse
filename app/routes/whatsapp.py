from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.whatsapp import SendMessageRequest, SendMessageResponse
from app.services.whatsapp_service import (
    send_whatsapp_message as send_whatsapp_message_service,
)

router = APIRouter(tags=["WhatsApp"])


@router.post("/send-message", response_model=SendMessageResponse)
async def send_whatsapp_message(
    payload: SendMessageRequest,
    workspace: Workspace = Depends(get_current_workspace),
) -> SendMessageResponse:
    try:
        result = await send_whatsapp_message_service(
            workspace_id=workspace.id,
            phone=payload.phone,
            message=payload.message,
        )
        return SendMessageResponse(**result)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except RuntimeError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
