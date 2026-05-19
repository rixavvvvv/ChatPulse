from fastapi.testclient import TestClient

from app.main import app
from app.routes import webhook_meta as webhook_meta_routes


def test_meta_webhook_verification_valid_token(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(webhook_meta_routes.settings, "meta_webhook_verify_token", "token-123")

    async def _empty_tokens(_session):
        return []

    monkeypatch.setattr(webhook_meta_routes, "list_all_webhook_verify_tokens", _empty_tokens)

    resp = client.get(
        "/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "token-123",
            "hub.challenge": "challenge-ok",
        },
    )
    assert resp.status_code == 200
    assert resp.text == "challenge-ok"


def test_meta_webhook_verification_invalid_token(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(webhook_meta_routes.settings, "meta_webhook_verify_token", "token-123")

    async def _empty_tokens(_session):
        return []

    monkeypatch.setattr(webhook_meta_routes, "list_all_webhook_verify_tokens", _empty_tokens)

    resp = client.get(
        "/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "wrong-token",
            "hub.challenge": "challenge-ok",
        },
    )
    assert resp.status_code == 403


def test_meta_webhook_verification_missing_token(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(webhook_meta_routes.settings, "meta_webhook_verify_token", "")

    async def _empty_tokens(_session):
        return []

    monkeypatch.setattr(webhook_meta_routes, "list_all_webhook_verify_tokens", _empty_tokens)

    resp = client.get(
        "/webhook/meta",
        params={
            "hub.mode": "subscribe",
            "hub.verify_token": "anything",
            "hub.challenge": "challenge-ok",
        },
    )
    assert resp.status_code == 403


def test_meta_webhook_signature_mismatch(monkeypatch):
    client = TestClient(app)
    monkeypatch.setattr(webhook_meta_routes.settings, "meta_app_secret", "secret-123")
    monkeypatch.setattr(webhook_meta_routes.settings, "webhook_ingest_rate_limit_per_ip_per_minute", 0)

    async def _empty_secrets(_session):
        return []

    monkeypatch.setattr(webhook_meta_routes, "list_all_app_secrets", _empty_secrets)

    resp = client.post(
        "/webhook/meta",
        headers={"X-Hub-Signature-256": "sha256=deadbeef"},
        json={"object": "whatsapp_business_account"},
    )
    assert resp.status_code == 401
