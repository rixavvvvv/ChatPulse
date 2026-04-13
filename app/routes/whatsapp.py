from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_db_session
from app.dependencies.workspace import get_current_workspace
from app.models.message_event import MessageEventStatus
from app.models.workspace import Workspace
from app.schemas.whatsapp import SendMessageRequest, SendMessageResponse
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.message_event_service import record_message_event
from app.services.webhook_service import register_sent_message
from app.services.whatsapp_service import (
    ApiError,
    InvalidNumberError,
    RateLimitError,
    send_whatsapp_message as send_whatsapp_message_service,
)

router = APIRouter(tags=["WhatsApp"])


@router.post("/send-message", response_model=SendMessageResponse)
async def send_whatsapp_message(
    payload: SendMessageRequest,
    workspace: Workspace = Depends(get_current_workspace),
    session: AsyncSession = Depends(get_db_session),
) -> SendMessageResponse:
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail="Raw message sending is disabled for outreach. Use approved templates via campaigns.",
    )

    try:
        await ensure_workspace_can_send(
            session=session,
            workspace_id=workspace.id,
            requested_count=1,
        )

        result = await send_whatsapp_message_service(
            workspace_id=workspace.id,
            phone=payload.phone,
            message=payload.message,
        )

        provider_message_id = result.get("message_id")
        if isinstance(provider_message_id, str) and provider_message_id.strip():
            await register_sent_message(
                session=session,
                workspace_id=workspace.id,
                provider_message_id=provider_message_id,
                recipient_phone=payload.phone,
            )
            await record_message_event(
                session=session,
                workspace_id=workspace.id,
                campaign_id=None,
                contact_id=None,
                status=MessageEventStatus.sent,
            )
            await session.commit()

        return SendMessageResponse(**result)
    except InvalidNumberError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        )
    except BillingLimitExceeded as exc:
        raise HTTPException(
            status_code=status.HTTP_402_PAYMENT_REQUIRED,
            detail=str(exc),
        )
    except RateLimitError as exc:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=str(exc),
        )
    except ApiError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        )
