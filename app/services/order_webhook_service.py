from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.ecommerce import EcommerceStoreConnection, OrderWebhookDeliveryLog, OrderWebhookLogStatus
from app.models.message_event import MessageEventStatus
from app.models.template import Template, TemplateCategory, TemplateStatus
from app.services.billing_service import BillingLimitExceeded, ensure_workspace_can_send
from app.services.contact_service import digits_for_whatsapp_cloud_api, normalize_phone
from app.services.ecommerce_store_service import get_store_by_identifier
from app.services.ecommerce_template_map_service import get_template_for_event
from app.services.message_event_service import record_message_event
from app.services.meta_template_params import build_order_event_template_parameters
from app.services.webhook_service import register_sent_message
from app.services.whatsapp_service import (
    ApiError,
    InvalidNumberError,
    RateLimitError,
    send_whatsapp_template_message,
)

logger = logging.getLogger(__name__)
settings = get_settings()

ORDER_CREATED = "order_created"
SIGNATURE_HEADERS = (
    "X-Shopify-Hmac-Sha256",
    "X-Webhook-Signature",
    "X-Signature",
)


def verify_hmac_sha256_base64(secret: str, raw_body: bytes, signature_header: str) -> bool:
    """Shopify-style HMAC: base64( HMAC-SHA256(secret, raw_body) )."""
    candidate = (signature_header or "").strip()
    if not candidate or not secret:
        return False
    try:
        mac = hmac.new(secret.encode("utf-8"), raw_body, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode("utf-8")
        return hmac.compare_digest(expected, candidate)
    except Exception:
        return False


def _first_signature_header(headers: Any) -> str | None:
    for key in SIGNATURE_HEADERS:
        val = headers.get(key) or headers.get(key.lower())
        if val:
            return val
    return None


def _extract_order_fields(data: dict[str, Any]) -> dict[str, str | None]:
    """Accept flat JSON or common Shopify order webhook shapes."""
    root: dict[str, Any] = data
    if isinstance(data.get("order"), dict):
        root = data["order"]

    customer: dict[str, Any] = {}
    if isinstance(root.get("customer"), dict):
        customer = root["customer"]

    first = (customer.get("first_name") or "").strip()
    last = (customer.get("last_name") or "").strip()
    combined_name = f"{first} {last}".strip()

    name = (
        data.get("customer_name")
        or data.get("name")
        or root.get("customer_name")
        or combined_name
        or None
    )
    if isinstance(name, str):
        name = name.strip() or None

    phone = (
        data.get("phone")
        or data.get("customer_phone")
        or root.get("phone")
        or customer.get("phone")
    )
    if not phone and isinstance(customer.get("default_address"), dict):
        phone = customer["default_address"].get("phone")

    order_id_raw = (
        data.get("order_id")
        or data.get("order_number")
        or root.get("order_number")
        or root.get("id")
        or root.get("name")
    )
    order_id = str(order_id_raw).strip() if order_id_raw is not None else None

    total_raw = (
        data.get("total_amount")
        or data.get("total_price")
        or root.get("total_price")
        or root.get("current_total_price")
    )
    total_str = str(total_raw).strip() if total_raw is not None else None

    if phone is not None:
        phone = str(phone).strip() or None

    return {
        "customer_name": name,
        "phone": phone,
        "order_id": order_id,
        "total_amount": total_str,
    }


def _preview_message(template_body: str, ctx: dict[str, str]) -> str:
    preview = template_body
    for key, val in ctx.items():
        preview = preview.replace(f"{{{{{key}}}}}", val)
    for idx, val in [
        ("1", ctx.get("name", "")),
        ("2", ctx.get("order_id", "")),
        ("3", ctx.get("amount", "")),
        ("4", ctx.get("phone", "")),
    ]:
        preview = preview.replace(f"{{{{{idx}}}}}", val)
    return preview[:4096]


async def _append_delivery_log(
    session: AsyncSession,
    *,
    workspace_id: int,
    store_connection_id: int | None,
    phone: str,
    message_preview: str,
    status: OrderWebhookLogStatus,
    error: str | None,
    attempts: int,
) -> None:
    row = OrderWebhookDeliveryLog(
        workspace_id=workspace_id,
        store_connection_id=store_connection_id,
        phone=phone,
        message_preview=message_preview,
        status=status.value,
        error=error,
        attempts=attempts,
    )
    session.add(row)
    await session.commit()


async def process_order_created_webhook(
    session: AsyncSession,
    *,
    store_identifier: str,
    raw_body: bytes,
    headers: Any,
) -> None:
    """Verify HMAC, parse payload, send WhatsApp template, log outcome. Does not raise for bad business data."""
    connection = await get_store_by_identifier(session, store_identifier=store_identifier)
    if not connection:
        logger.warning(
            "order webhook: unknown store_identifier=%s", store_identifier)
        return

    secret = _plaintext_secret(connection)
    sig = _first_signature_header(headers)
    if not sig or not verify_hmac_sha256_base64(secret, raw_body, sig):
        logger.warning(
            "order webhook: invalid HMAC for store_identifier=%s", store_identifier)
        raise PermissionError("Invalid webhook signature")

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        logger.warning(
            "order webhook: invalid JSON for store=%s: %s", store_identifier, exc)
        return

    if not isinstance(payload, dict):
        logger.warning("order webhook: payload not an object store=%s", store_identifier)
        return

    fields = _extract_order_fields(payload)
    phone_raw = fields["phone"]
    name = fields["customer_name"] or "Customer"
    order_id = fields["order_id"] or ""
    amount = fields["total_amount"] or ""

    if not phone_raw:
        logger.warning(
            "order webhook: missing phone store=%s payload_keys=%s",
            store_identifier,
            list(payload.keys())[:20],
        )
        await _append_delivery_log(
            session,
            workspace_id=connection.workspace_id,
            store_connection_id=connection.id,
            phone="",
            message_preview="(no phone)",
            status=OrderWebhookLogStatus.failed,
            error="Missing phone number in payload",
            attempts=0,
        )
        return

    normalized = normalize_phone(phone_raw)
    if not normalized:
        logger.warning(
            "order webhook: invalid phone format store=%s phone=%s",
            store_identifier,
            phone_raw,
        )
        await _append_delivery_log(
            session,
            workspace_id=connection.workspace_id,
            store_connection_id=connection.id,
            phone=phone_raw,
            message_preview="(invalid phone)",
            status=OrderWebhookLogStatus.failed,
            error="Invalid phone number format",
            attempts=0,
        )
        return

    api_digits = digits_for_whatsapp_cloud_api(
        normalized,
        settings.whatsapp_default_calling_code,
    )
    if not api_digits:
        await _append_delivery_log(
            session,
            workspace_id=connection.workspace_id,
            store_connection_id=connection.id,
            phone=phone_raw,
            message_preview="(invalid phone for API)",
            status=OrderWebhookLogStatus.failed,
            error="Could not normalize phone for WhatsApp API",
            attempts=0,
        )
        return

    template = await get_template_for_event(
        session,
        workspace_id=connection.workspace_id,
        event_type=ORDER_CREATED,
    )
    if not template:
        logger.warning(
            "order webhook: no template mapped for %s workspace=%s",
            ORDER_CREATED,
            connection.workspace_id,
        )
        await _append_delivery_log(
            session,
            workspace_id=connection.workspace_id,
            store_connection_id=connection.id,
            phone=api_digits,
            message_preview="(no template mapping)",
            status=OrderWebhookLogStatus.failed,
            error=f"No template mapped for event '{ORDER_CREATED}'",
            attempts=0,
        )
        return

    if template.status != TemplateStatus.approved or not template.meta_template_id:
        await _append_delivery_log(
            session,
            workspace_id=connection.workspace_id,
            store_connection_id=connection.id,
            phone=api_digits,
            message_preview=template.name,
            status=OrderWebhookLogStatus.failed,
            error="Mapped template is not approved or not synced with Meta",
            attempts=0,
        )
        return

    if template.category != TemplateCategory.UTILITY.value:
        logger.info(
            "order webhook: template %s category=%s (UTILITY recommended for transactional sends)",
            template.id,
            template.category,
        )

    ctx_strings = {
        "name": name,
        "customer_name": name,
        "order_id": order_id,
        "amount": amount,
        "total_amount": amount,
        "phone": api_digits,
    }
    preview = _preview_message(template.body_text, ctx_strings)

    body_parameters = build_order_event_template_parameters(
        template.body_text,
        customer_name=name,
        order_id=order_id,
        amount=amount,
        phone=api_digits,
    )
    header_parameters = build_order_event_template_parameters(
        template.header_content or "",
        customer_name=name,
        order_id=order_id,
        amount=amount,
        phone=api_digits,
    )

    last_error: str | None = None
    attempts_used = 0
    for attempt in range(1, 4):
        attempts_used = attempt
        try:
            await ensure_workspace_can_send(
                session=session,
                workspace_id=connection.workspace_id,
                requested_count=1,
            )
            send_result = await send_whatsapp_template_message(
                workspace_id=connection.workspace_id,
                phone=phone_raw,
                template_name=template.name,
                language=template.language,
                body_parameters=body_parameters or None,
                header_parameters=header_parameters or None,
            )
            provider_message_id = send_result.get("message_id")
            if isinstance(provider_message_id, str) and provider_message_id.strip():
                await register_sent_message(
                    session=session,
                    workspace_id=connection.workspace_id,
                    provider_message_id=provider_message_id,
                    recipient_phone=api_digits,
                )
            await record_message_event(
                session=session,
                workspace_id=connection.workspace_id,
                campaign_id=None,
                contact_id=None,
                status=MessageEventStatus.sent,
            )
            await session.commit()
            await _append_delivery_log(
                session,
                workspace_id=connection.workspace_id,
                store_connection_id=connection.id,
                phone=api_digits,
                message_preview=preview,
                status=OrderWebhookLogStatus.success,
                error=None,
                attempts=attempts_used,
            )
            return
        except BillingLimitExceeded as exc:
            last_error = str(exc)
            attempts_used = attempt
            break
        except (ApiError, InvalidNumberError, RateLimitError) as exc:
            last_error = str(exc)
            if attempt < 3:
                delay = 0.5 * attempt
                await asyncio.sleep(delay)
        except Exception as exc:
            logger.exception("order webhook: unexpected send error")
            last_error = str(exc)
            if attempt < 3:
                await asyncio.sleep(0.5 * attempt)

    await _append_delivery_log(
        session,
        workspace_id=connection.workspace_id,
        store_connection_id=connection.id,
        phone=api_digits,
        message_preview=preview,
        status=OrderWebhookLogStatus.failed,
        error=last_error or "Send failed",
        attempts=attempts_used,
    )


def _plaintext_secret(connection: EcommerceStoreConnection) -> str:
    from app.services.ecommerce_store_service import get_webhook_secret_plaintext

    return get_webhook_secret_plaintext(connection)
