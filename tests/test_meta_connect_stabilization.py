from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies.workspace import get_current_workspace
from app.main import app
from app.routes import meta_credentials as meta_routes


async def _override_db():
    yield SimpleNamespace()


def _override_workspace():
    return SimpleNamespace(id=1)


def _payload():
    return {
        "phone_number_id": "1076773055521692",
        "business_account_id": "1284600699974738",
        "access_token": "token",
    }


def test_meta_connect_succeeds_when_subscription_sync_fails(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[get_current_workspace] = _override_workspace
    app.dependency_overrides[meta_routes.get_db_session] = _override_db

    async def _validate(**kwargs):
        return None

    async def _upsert(**kwargs):
        return SimpleNamespace(
            phone_number_id=kwargs["phone_number_id"],
            business_account_id=kwargs["business_account_id"],
        )

    async def _subscribe(**kwargs):
        raise RuntimeError("subscription failed")

    monkeypatch.setattr(meta_routes, "validate_meta_cloud_credentials", _validate)
    monkeypatch.setattr(meta_routes, "upsert_workspace_meta_credential", _upsert)
    monkeypatch.setattr(meta_routes, "ensure_waba_app_subscription", _subscribe)

    resp = client.post("/meta/connect", json=_payload())
    assert resp.status_code == 200
    assert resp.json()["is_connected"] is True

    app.dependency_overrides.clear()

