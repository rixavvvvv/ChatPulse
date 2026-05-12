import logging
from typing import Any

import httpx

from app.core.config import get_settings
from app.services.contact_service import digits_for_whatsapp_cloud_api, normalize_phone
from app.services.meta_credential_service import (
    WorkspaceMetaCredentials,
    get_workspace_meta_credentials,
)

logger = logging.getLogger(__name__)
settings = get_settings()


class WhatsAppSendError(RuntimeError):
    failure_classification: str = "api_error"
    retryable: bool = False

    def __init__(self, message: str):
        super().__init__(message)


class InvalidNumberError(WhatsAppSendError):
    failure_classification = "invalid_number"
    retryable = False


class RateLimitError(WhatsAppSendError):
    failure_classification = "rate_limit"
    retryable = True


class ApiError(WhatsAppSendError):
    failure_classification = "api_error"

    def __init__(self, message: str, retryable: bool):
        super().__init__(message)
        self.retryable = retryable


class WhatsAppService:
    async def send_whatsapp_message(
        self,
        workspace_id: int,
        phone: str,
        message: str,
    ) -> dict[str, str | None]:
        if settings.whatsapp_provider != "cloud":
            raise ApiError(
                "WHATSAPP_PROVIDER must be set to 'cloud' for real message sending",
                retryable=False,
            )

        normalized_phone = normalize_phone(phone)
        if not normalized_phone:
            raise InvalidNumberError("Invalid phone number format")

        api_to = digits_for_whatsapp_cloud_api(
            normalized_phone,
            settings.whatsapp_default_calling_code,
        )
        if not api_to:
            raise InvalidNumberError("Invalid phone number format for WhatsApp API")

        if not message.strip():
            raise ApiError("Message cannot be empty", retryable=False)

        credentials = await get_workspace_meta_credentials(workspace_id)
        if not credentials:
            raise ApiError(
                "Meta credentials are not configured for this workspace",
                retryable=False,
            )

        return await self._send_via_cloud_api(
            phone=api_to,
            payload={
                "messaging_product": "whatsapp",
                "to": api_to,
                "type": "text",
                "text": {"body": message},
            },
            credentials=credentials,
            workspace_id=workspace_id,
            request_kind="text",
        )

    async def send_whatsapp_template_message(
        self,
        workspace_id: int,
        phone: str,
        template_name: str,
        language: str,
        body_parameters: list[str] | None = None,
        header_parameters: list[str] | None = None,
    ) -> dict[str, str | None]:
        if settings.whatsapp_provider != "cloud":
            raise ApiError(
                "WHATSAPP_PROVIDER must be set to 'cloud' for real message sending",
                retryable=False,
            )

        normalized_phone = normalize_phone(phone)
        if not normalized_phone:
            raise InvalidNumberError("Invalid phone number format")

        api_to = digits_for_whatsapp_cloud_api(
            normalized_phone,
            settings.whatsapp_default_calling_code,
        )
        if not api_to:
            raise InvalidNumberError("Invalid phone number format for WhatsApp API")

        if not template_name.strip():
            raise ApiError("Template name is required", retryable=False)

        credentials = await get_workspace_meta_credentials(workspace_id)
        if not credentials:
            raise ApiError(
                "Meta credentials are not configured for this workspace",
                retryable=False,
            )

        components: list[dict[str, Any]] = []
        if body_parameters:
            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": value} for value in body_parameters
                    ],
                }
            )
        if header_parameters:
            components.append(
                {
                    "type": "header",
                    "parameters": [
                        {"type": "text", "text": value} for value in header_parameters
                    ],
                }
            )

        template_payload: dict[str, Any] = {
            "name": template_name,
            "language": {"code": language.strip() or "en_US"},
        }
        if components:
            template_payload["components"] = components

        return await self._send_via_cloud_api(
            phone=api_to,
            payload={
                "messaging_product": "whatsapp",
                "to": api_to,
                "type": "template",
                "template": template_payload,
            },
            credentials=credentials,
            workspace_id=workspace_id,
            request_kind="template",
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
        payload: dict[str, Any],
        credentials: WorkspaceMetaCredentials,
        workspace_id: int,
        request_kind: str,
    ) -> dict[str, str | None]:
        logger.info(
            "Cloud %s send requested for workspace_id=%s phone_number_id=%s recipient=%s",
            request_kind,
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
            raise ApiError("Meta Graph API request timed out",
                           retryable=True) from exc
        except httpx.HTTPError as exc:
            logger.warning(
                "Meta Graph API transport error workspace_id=%s phone_number_id=%s recipient=%s",
                workspace_id,
                credentials.phone_number_id,
                phone,
            )
            raise ApiError("Meta Graph API transport error",
                           retryable=True) from exc

        response_json: Any
        try:
            response_json = response.json()
        except ValueError:
            response_json = None

        if response.status_code >= 400:
            error_message = self._extract_error_message(response_json)
            error_code: int | None = None
            if isinstance(response_json, dict):
                error_block = response_json.get("error")
                if isinstance(error_block, dict):
                    error_code_raw = error_block.get("code")
                    if isinstance(error_code_raw, int):
                        error_code = error_code_raw
            logger.warning(
                "Meta Graph API rejected request workspace_id=%s phone_number_id=%s status_code=%s error=%s",
                workspace_id,
                credentials.phone_number_id,
                response.status_code,
                error_message,
            )

            error_text = error_message.lower()
            if (
                response.status_code == 429
                or error_code in {4, 17, 613, 80007, 130429}
                or "rate limit" in error_text
            ):
                raise RateLimitError(
                    f"Meta Graph API rate limit: {error_message}")

            if (
                response.status_code == 400
                and (
                    "invalid phone" in error_text
                    or "invalid recipient" in error_text
                    or "phone number" in error_text and "invalid" in error_text
                )
            ):
                raise InvalidNumberError(
                    f"Meta Graph API invalid number: {error_message}")

            retryable = response.status_code >= 500
            raise ApiError(
                f"Meta Graph API error: {error_message}", retryable=retryable)

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


async def send_whatsapp_template_message(
    workspace_id: int,
    phone: str,
    template_name: str,
    language: str,
    body_parameters: list[str] | None = None,
    header_parameters: list[str] | None = None,
) -> dict[str, str | None]:
    return await whatsapp_service.send_whatsapp_template_message(
        workspace_id=workspace_id,
        phone=phone,
        template_name=template_name,
        language=language,
        body_parameters=body_parameters,
        header_parameters=header_parameters,
    )


async def validate_meta_cloud_credentials(
    phone_number_id: str,
    business_account_id: str,
    access_token: str,
) -> None:
    base_url = f"{settings.meta_graph_api_base_url}/{settings.meta_graph_api_version}"
    headers = {
        "Authorization": f"Bearer {access_token}",
    }

    async def _validate_entity(entity_id: str, entity_type: str) -> None:
        url = f"{base_url}/{entity_id}"
        try:
            async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
                response = await client.get(url, headers=headers, params={"fields": "id"})
        except httpx.TimeoutException as exc:
            raise ApiError(
                f"Meta Graph API timeout while validating {entity_type}",
                retryable=True,
            ) from exc
        except httpx.HTTPError as exc:
            raise ApiError(
                f"Meta Graph API transport error while validating {entity_type}",
                retryable=True,
            ) from exc

        payload: Any
        try:
            payload = response.json()
        except ValueError:
            payload = None

        if response.status_code >= 400:
            error_message = WhatsAppService._extract_error_message(payload)
            raise ApiError(
                f"Invalid Meta {entity_type}: {error_message}",
                retryable=False,
            )

        returned_id = None
        if isinstance(payload, dict):
            candidate = payload.get("id")
            if isinstance(candidate, str):
                returned_id = candidate

        if returned_id and returned_id != entity_id:
            raise ApiError(
                f"Meta {entity_type} mismatch. Expected {entity_id}, got {returned_id}",
                retryable=False,
            )

    await _validate_entity(phone_number_id, "phone number ID")
    await _validate_entity(business_account_id, "business account ID")
