from fastapi import APIRouter, Depends, HTTPException, status

from app.dependencies.workspace import get_current_workspace
from app.models.workspace import Workspace
from app.schemas.whatsapp import SendMessageRequest, SendMessageResponse

router = APIRouter(tags=["WhatsApp"])


@router.post("/send-message", response_model=SendMessageResponse)
async def send_whatsapp_message(
    _payload: SendMessageRequest,
    _workspace: Workspace = Depends(get_current_workspace),
) -> SendMessageResponse:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Raw message sending is disabled for outreach. Use approved templates via campaigns.",
    )
