import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.contact_service import normalize_phone
from app.services.meta_credential_service import (
    WorkspaceMetaCredentials,
    get_workspace_meta_credentials,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class WhatsAppService:
    async def send_whatsapp_message(
        self,
        workspace_id: int,
        phone: str,
        message: str,
    ) -> dict[str, str | None]:
        normalized_phone = normalize_phone(phone)
        if not normalized_phone:
            raise ValueError("Invalid phone number format")

        if not message.strip():
            raise ValueError("Message cannot be empty")

        credentials = await get_workspace_meta_credentials(workspace_id)
        if not credentials:
            raise ValueError(
                "Meta credentials are not configured for this workspace")

        return await self._send_via_cloud_api(
            phone=normalized_phone,
            message=message,
            credentials=credentials,
            workspace_id=workspace_id,
        )

    async def send_message(
        self,
        phone: str,
        message: str,
        workspace_id: int | None = None,
    ) -> dict[str, str | None]:
        if workspace_id is None:
            raise ValueError("workspace_id is required")
        return await self.send_whatsapp_message(
            workspace_id=workspace_id,
            phone=phone,
            message=message,
        )

    @staticmethod
    def _extract_error_message(response_json: Any) -> str:
        if not isinstance(response_json, dict):
            return "Unknown Meta Graph API error"

        error = response_json.get("error")
        if isinstance(error, dict):
            message = error.get("message")
            if isinstance(message, str) and message.strip():
                return message

        return "Unknown Meta Graph API error"

    async def _send_via_cloud_api(
        self,
        phone: str,
        message: str,
        credentials: WorkspaceMetaCredentials,
        workspace_id: int,
    ) -> dict[str, str | None]:
        logger.info(
            "Cloud send requested for workspace_id=%s phone_number_id=%s recipient=%s",
            workspace_id,
            credentials.phone_number_id,
            phone,
        )

        url = (
            f"{settings.meta_graph_api_base_url}/"
            f"{settings.meta_graph_api_version}/"
            f"{credentials.phone_number_id}/messages"
        )

        headers = {
            "Authorization": f"Bearer {credentials.access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": phone,
            "type": "text",
            "text": {"body": message},
        }

        try:
            async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
                response = await client.post(url, headers=headers, json=payload)
        except httpx.TimeoutException as exc:
            logger.warning(
                "Meta Graph API timeout workspace_id=%s phone_number_id=%s recipient=%s",
                workspace_id,
                credentials.phone_number_id,
                phone,
            )
            raise RuntimeError("Meta Graph API request timed out") from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Meta Graph API transport error workspace_id=%s phone_number_id=%s recipient=%s",
                workspace_id,
                credentials.phone_number_id,
                phone,
            )
            raise RuntimeError("Meta Graph API transport error") from exc

        response_json: Any
        try:
            response_json = response.json()
        except ValueError:
            response_json = None

        if response.status_code >= 400:
            error_message = self._extract_error_message(response_json)
            logger.warning(
                "Meta Graph API rejected request workspace_id=%s phone_number_id=%s status_code=%s error=%s",
                workspace_id,
                credentials.phone_number_id,
                response.status_code,
                error_message,
            )
            raise RuntimeError(f"Meta Graph API error: {error_message}")

        message_id = None
        if isinstance(response_json, dict):
            messages = response_json.get("messages")
            if isinstance(messages, list) and messages:
                first = messages[0]
                if isinstance(first, dict):
                    candidate = first.get("id")
                    if isinstance(candidate, str):
                        message_id = candidate

        return {
            "status": "sent",
            "phone": phone,
            "provider": "cloud",
            "message_id": message_id,
        }


whatsapp_service = WhatsAppService()


async def send_message(
    phone: str,
    message: str,
    workspace_id: int | None = None,
) -> dict[str, str | None]:
    return await whatsapp_service.send_message(
        phone=phone,
        message=message,
        workspace_id=workspace_id,
    )


async def send_whatsapp_message(
    workspace_id: int,
    phone: str,
    message: str,
) -> dict[str, str | None]:
    return await whatsapp_service.send_whatsapp_message(
        workspace_id=workspace_id,
        phone=phone,
        message=message,
    )
