import re
from collections.abc import Sequence

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.models.template import (
    Template,
    TemplateCategory,
    TemplateHeaderType,
    TemplateStatus,
)
from app.schemas.template import TemplateButtonInput
from app.services.meta_credential_service import get_workspace_meta_credentials

settings = get_settings()

VARIABLE_PATTERN = re.compile(r"\{\{\d+\}\}")
SUPPORTED_BUTTON_TYPES = {"quick_reply", "url", "phone_number", "copy_code"}


def _extract_placeholder_indexes(text: str) -> list[int]:
    indexes: list[int] = []
    seen: set[int] = set()
    for match in VARIABLE_PATTERN.finditer(text):
        token = match.group(0)
        number = int(token.replace("{{", "").replace("}}", "").strip())
        if number in seen:
            continue
        seen.add(number)
        indexes.append(number)
    indexes.sort()
    return indexes


def _normalize_variables(body_text: str, variables: Sequence[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()

    source = list(variables)
    if not source:
        source = VARIABLE_PATTERN.findall(body_text)

    for token in source:
        normalized = token.strip()
        if not VARIABLE_PATTERN.fullmatch(normalized):
            raise ValueError("variables must use Meta format like {{1}}, {{2}}")
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)

    return cleaned


def _validate_buttons(buttons: Sequence[TemplateButtonInput]) -> None:
    if len(buttons) > 3:
        raise ValueError("max buttons allowed is 3")

    for button in buttons:
        if button.type not in SUPPORTED_BUTTON_TYPES:
            raise ValueError(f"unsupported button type: {button.type}")

        if button.type == "quick_reply":
            continue

        if not button.value.strip():
            raise ValueError(f"button value is required for type {button.type}")


def _normalize_sample_values(
    placeholders: Sequence[str],
    sample_values: Sequence[str],
) -> list[str]:
    if not placeholders:
        return []

    normalized: list[str] = [
        value.strip() for value in sample_values if isinstance(value, str) and value.strip()
    ]

    while len(normalized) < len(placeholders):
        normalized.append(f"Sample {len(normalized) + 1}")

    return normalized[: len(placeholders)]


def _build_meta_components(template: Template) -> list[dict]:
    components: list[dict] = []

    if template.header_type != TemplateHeaderType.none.value:
        if not template.header_content or not template.header_content.strip():
            raise ValueError("header_content is required when header_type is not none")

        format_value = template.header_type.upper()
        header_component: dict = {
            "type": "HEADER",
            "format": format_value,
        }
        if template.header_type == TemplateHeaderType.text.value:
            header_component["text"] = template.header_content
            header_indexes = _extract_placeholder_indexes(template.header_content)
            if header_indexes:
                header_component["example"] = {
                    "header_text": [f"Sample {index}" for index in header_indexes]
                }
        else:
            # Meta requires media template examples; header_content should be a valid sample handle or URL.
            header_component["example"] = {"header_handle": [template.header_content]}
        components.append(header_component)

    body_component: dict = {
        "type": "BODY",
        "text": template.body_text,
    }
    if template.variables:
        body_examples = [
            value for value in template.body_examples if isinstance(value, str) and value.strip()
        ]
        if len(body_examples) < len(template.variables):
            body_examples = _normalize_sample_values(template.variables, body_examples)
        body_component["example"] = {"body_text": [body_examples]}
    components.append(body_component)

    if template.footer_text and template.footer_text.strip():
        components.append(
            {
                "type": "FOOTER",
                "text": template.footer_text,
            }
        )

    if template.buttons:
        meta_buttons: list[dict] = []
        for button in template.buttons:
            button_type = str(button.get("type", "")).strip().lower()
            text = str(button.get("text", "")).strip()
            value = str(button.get("value", "")).strip()

            if button_type == "quick_reply":
                meta_buttons.append({"type": "QUICK_REPLY", "text": text})
            elif button_type == "url":
                meta_buttons.append({"type": "URL", "text": text, "url": value})
            elif button_type == "phone_number":
                meta_buttons.append({"type": "PHONE_NUMBER", "text": text, "phone_number": value})
            elif button_type == "copy_code":
                meta_buttons.append({"type": "COPY_CODE", "text": text, "example": [value]})

        if meta_buttons:
            components.append(
                {
                    "type": "BUTTONS",
                    "buttons": meta_buttons,
                }
            )

    return components


def _map_meta_status(status_text: str | None) -> TemplateStatus:
    normalized = (status_text or "").strip().upper()
    if normalized == "APPROVED":
        return TemplateStatus.approved
    if normalized in {"REJECTED", "DISABLED"}:
        return TemplateStatus.rejected
    if normalized in {"PENDING", "PENDING_REVIEW", "IN_REVIEW"}:
        return TemplateStatus.pending
    return TemplateStatus.pending


async def create_template(
    session: AsyncSession,
    workspace_id: int,
    name: str,
    language: str,
    category: TemplateCategory,
    header_type: TemplateHeaderType,
    header_content: str | None,
    body_text: str,
    variables: list[str],
    sample_values: list[str],
    footer_text: str | None,
    buttons: list[TemplateButtonInput],
) -> Template:
    normalized_body = body_text.strip()
    if not normalized_body:
        raise ValueError("body_text is required")

    cleaned_variables = _normalize_variables(normalized_body, variables)
    normalized_examples = _normalize_sample_values(cleaned_variables, sample_values)
    _validate_buttons(buttons)

    template = Template(
        workspace_id=workspace_id,
        name=name.strip(),
        body=normalized_body,
        language=language.strip() or "en_US",
        category=category.value,
        header_type=header_type.value,
        header_content=header_content.strip() if header_content and header_content.strip() else None,
        body_text=normalized_body,
        variables=cleaned_variables,
        body_examples=normalized_examples,
        footer_text=footer_text.strip() if footer_text and footer_text.strip() else None,
        buttons=[button.model_dump() for button in buttons],
        status=TemplateStatus.draft,
        meta_template_id=None,
        rejection_reason=None,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template)
    return template


async def list_templates(
    session: AsyncSession,
    workspace_id: int,
) -> list[Template]:
    stmt = (
        select(Template)
        .where(Template.workspace_id == workspace_id)
        .order_by(Template.created_at.desc())
    )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def get_template_by_id(
    session: AsyncSession,
    workspace_id: int,
    template_id: int,
) -> Template | None:
    stmt = select(Template).where(
        Template.workspace_id == workspace_id,
        Template.id == template_id,
    )
    result = await session.execute(stmt)
    return result.scalar_one_or_none()


async def update_template_status(
    session: AsyncSession,
    template: Template,
    status: TemplateStatus,
) -> Template:
    template.status = status
    await session.commit()
    await session.refresh(template)
    return template


async def submit_template_to_meta(
    session: AsyncSession,
    workspace_id: int,
    template: Template,
) -> Template:
    if template.status == TemplateStatus.approved:
        return template

    credentials = await get_workspace_meta_credentials(workspace_id)
    if not credentials:
        raise ValueError("Meta credentials are not configured for this workspace")

    payload = {
        "name": template.name,
        "language": template.language,
        "category": template.category,
        "components": _build_meta_components(template),
    }
    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/"
        f"{credentials.business_account_id}/message_templates"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
            response = await client.post(
                url,
                headers={
                    "Authorization": f"Bearer {credentials.access_token}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Meta API timeout while submitting template") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Meta API transport error while submitting template") from exc

    response_payload: dict = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            response_payload = parsed
    except ValueError:
        response_payload = {}

    if response.status_code >= 400:
        detail = "Meta template submission failed"
        error_block = response_payload.get("error")
        if isinstance(error_block, dict):
            message = error_block.get("message")
            if isinstance(message, str) and message.strip():
                detail = message
        raise ValueError(detail)

    meta_template_id = response_payload.get("id")
    if isinstance(meta_template_id, str) and meta_template_id.strip():
        template.meta_template_id = meta_template_id

    template.status = TemplateStatus.pending
    template.rejection_reason = None
    await session.commit()
    await session.refresh(template)
    return template


async def sync_template_status_from_meta(
    session: AsyncSession,
    workspace_id: int,
    template: Template,
) -> Template:
    credentials = await get_workspace_meta_credentials(workspace_id)
    if not credentials:
        raise ValueError("Meta credentials are not configured for this workspace")

    if not template.meta_template_id and template.status == TemplateStatus.draft:
        raise ValueError("Template is draft and has not been submitted to Meta yet")

    url = (
        f"{settings.meta_graph_api_base_url}/"
        f"{settings.meta_graph_api_version}/"
        f"{credentials.business_account_id}/message_templates"
    )

    try:
        async with httpx.AsyncClient(timeout=settings.meta_api_timeout_seconds) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {credentials.access_token}"},
                params={
                    "name": template.name,
                    "fields": "id,name,status,rejected_reason",
                    "limit": 50,
                },
            )
    except httpx.TimeoutException as exc:
        raise RuntimeError("Meta API timeout while syncing template status") from exc
    except httpx.HTTPError as exc:
        raise RuntimeError("Meta API transport error while syncing template status") from exc

    payload: dict = {}
    try:
        parsed = response.json()
        if isinstance(parsed, dict):
            payload = parsed
    except ValueError:
        payload = {}

    if response.status_code >= 400:
        detail = "Meta template status sync failed"
        error_block = payload.get("error")
        if isinstance(error_block, dict):
            message = error_block.get("message")
            if isinstance(message, str) and message.strip():
                detail = message
        raise ValueError(detail)

    data = payload.get("data") if isinstance(payload.get("data"), list) else []
    matched: dict | None = None
    for item in data:
        if not isinstance(item, dict):
            continue
        if template.meta_template_id and item.get("id") == template.meta_template_id:
            matched = item
            break
        if item.get("name") == template.name:
            matched = item

    if not matched:
        raise ValueError("Template not found on Meta for this business account")

    meta_status = matched.get("status")
    template.status = _map_meta_status(meta_status)
    if isinstance(matched.get("id"), str):
        template.meta_template_id = matched["id"]

    reason = matched.get("rejected_reason")
    template.rejection_reason = reason if isinstance(reason, str) and reason.strip() else None

    await session.commit()
    await session.refresh(template)
    return template
