from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from app.core.config import get_settings

settings = get_settings()


def meta_signature_valid(raw_body: bytes, signature_header: str | None) -> bool:
    if not settings.meta_app_secret:
        return True
    if not signature_header or not signature_header.strip():
        return False
    candidate = signature_header.strip()
    prefix = "sha256="
    if candidate.lower().startswith(prefix):
        candidate = candidate[len(prefix) :]
    if not candidate:
        return False
    computed = hmac.new(
        key=settings.meta_app_secret.encode("utf-8"),
        msg=raw_body,
        digestmod=hashlib.sha256,
    ).hexdigest()
    return hmac.compare_digest(computed, candidate)


def meta_challenge_response(
    hub_mode: str | None,
    hub_verify_token: str | None,
    hub_challenge: str | None,
) -> str | None:
    mode = (hub_mode or "").strip().lower()
    verify_token = (hub_verify_token or "").strip()
    challenge = (hub_challenge or "").strip()
    if mode == "subscribe" and verify_token == settings.meta_webhook_verify_token and challenge:
        return hub_challenge or challenge
    return None


def payload_sha256(raw_body: bytes) -> str:
    return hashlib.sha256(raw_body).hexdigest()


def webhook_dedupe_key(*, source: str, raw_body: bytes, store_fragment: str | None = None) -> str:
    h = hashlib.sha256()
    if store_fragment:
        h.update(store_fragment.encode("utf-8"))
        h.update(b"\x00")
    h.update(raw_body)
    return h.hexdigest()


def summarize_headers(headers: Any) -> dict[str, Any]:
    """Store non-secret diagnostic metadata only."""
    if headers is None:
        return {}
    try:
        items = headers.items() if hasattr(headers, "items") else []
    except Exception:
        return {}
    out: dict[str, Any] = {}
    for k, v in items:
        lk = str(k).lower()
        if lk in (
            "x-hub-signature-256",
            "x-shopify-hmac-sha256",
            "authorization",
            "cookie",
            "x-webhook-signature",
        ):
            out[str(k)] = "[redacted]"
        else:
            out[str(k)] = str(v)[:512]
    return out


def parse_json_object(raw_body: bytes) -> dict[str, Any]:
    payload = json.loads(raw_body.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("payload must be a JSON object")
    return payload
