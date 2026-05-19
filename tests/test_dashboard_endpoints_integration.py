from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_current_workspace
from app.main import app
from app.routes.dashboard import get_dashboard_service
from app.services.analytics_service import AnalyticsQueryService


class _DashboardServiceOK:
    async def get_dashboard_overview(self, **kwargs):
        return {"workspace_id": kwargs["workspace_id"], "total_messages_sent": 0}

    async def get_realtime_metrics(self, **kwargs):
        return {
            "workspace_id": kwargs["workspace_id"],
            "updated_at": "2026-01-01T00:00:00+00:00",
            "active_campaigns": 0,
            "messages_in_flight": 0,
            "queue_depth": 0,
            "active_workers": 0,
            "messages_last_minute": 0,
            "messages_last_hour": 0,
            "messages_per_second": 0.0,
            "avg_queue_latency_ms": None,
            "avg_dispatch_latency_ms": None,
            "p95_dispatch_latency_ms": None,
            "error_rate_percent": 0.0,
        }

    async def get_queue_health(self, **kwargs):
        return {"summary": {"workspace_id": kwargs["workspace_id"]}, "timeline": [], "error_breakdown": {}, "by_worker": {}}

    async def get_webhook_health(self, **kwargs):
        return {"summary": {"workspace_id": kwargs["workspace_id"]}, "timeline": [], "recent_failures": [], "by_source": {}}

    async def get_retry_analytics(self, **kwargs):
        return {"summary": {"workspace_id": kwargs["workspace_id"]}, "timeline": [], "top_retry_error_types": [], "by_error_type": {}}

    async def get_recovery_analytics(self, **kwargs):
        return {"summary": {"workspace_id": kwargs["workspace_id"]}, "timeline": [], "recent_recoveries": []}


class _DashboardServiceFail:
    async def get_dashboard_overview(self, **kwargs):
        raise RuntimeError("boom")

    async def get_realtime_metrics(self, **kwargs):
        raise RuntimeError("boom")

    async def get_queue_health(self, **kwargs):
        raise RuntimeError("boom")

    async def get_webhook_health(self, **kwargs):
        raise RuntimeError("boom")

    async def get_retry_analytics(self, **kwargs):
        raise RuntimeError("boom")

    async def get_recovery_analytics(self, **kwargs):
        raise RuntimeError("boom")


def _override_auth():
    return SimpleNamespace(id=1, role="user")


def _override_workspace():
    return SimpleNamespace(id=1)


def test_dashboard_endpoints_success_and_fallback(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _override_auth
    app.dependency_overrides[get_current_workspace] = _override_workspace

    # success path
    app.dependency_overrides[get_dashboard_service] = lambda: _DashboardServiceOK()
    endpoints = [
        "/dashboard/overview",
        "/dashboard/realtime",
        "/dashboard/queue/health",
        "/dashboard/webhooks/health",
        "/dashboard/analytics/retry",
        "/dashboard/analytics/recovery",
    ]
    for path in endpoints:
        resp = client.get(path)
        assert resp.status_code == 200

    # fallback path (must not 500)
    app.dependency_overrides[get_dashboard_service] = lambda: _DashboardServiceFail()
    for path in endpoints:
        resp = client.get(path)
        assert resp.status_code == 200

    app.dependency_overrides.clear()


def test_analytics_dashboard_and_realtime_workspace_isolated(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _override_auth
    app.dependency_overrides[get_current_workspace] = _override_workspace

    async def _workspace_metrics(*args, **kwargs):
        return SimpleNamespace(
            workspace_id=1,
            messages_sent=0,
            campaigns_completed=0,
            message_delivery_rate=0.0,
        )

    async def _realtime_metrics(*args, **kwargs):
        return {
            "workspace_id": 1,
            "updated_at": "2026-01-01T00:00:00+00:00",
            "active_campaigns": 0,
            "messages_in_flight": 0,
            "queue_depth": 0,
            "active_workers": 0,
            "messages_last_minute": 0,
            "messages_last_hour": 0,
            "messages_per_second": 0.0,
            "avg_queue_latency_ms": None,
            "avg_dispatch_latency_ms": None,
            "p95_dispatch_latency_ms": None,
            "error_rate_percent": 0.0,
        }

    async def _rollups(*args, **kwargs):
        return []

    monkeypatch.setattr(AnalyticsQueryService, "get_workspace_metrics", _workspace_metrics)
    monkeypatch.setattr(AnalyticsQueryService, "get_realtime_metrics", _realtime_metrics)
    monkeypatch.setattr(AnalyticsQueryService, "get_rollups", _rollups)

    ok1 = client.get("/analytics/workspace/dashboard")
    ok2 = client.get("/analytics/realtime")
    deny1 = client.get("/analytics/workspace/dashboard?workspace_id=999")
    deny2 = client.get("/analytics/realtime?workspace_id=999")

    assert ok1.status_code == 200
    assert ok2.status_code == 200
    assert deny1.status_code == 403
    assert deny2.status_code == 403

    app.dependency_overrides.clear()
