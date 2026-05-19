from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app.dependencies.auth import get_current_user
from app.dependencies.workspace import get_workspace_id
from app.main import app
from app.models.workflow import WorkflowStatus
from app.routes import workflows as workflow_routes
from app.routes.workflows import router as workflows_router


def _override_user():
    return SimpleNamespace(id=1, role="user")


def _override_workspace_id():
    return 1


async def _override_db():
    yield SimpleNamespace()


def _valid_workflow_payload():
    return {
        "name": "Workflow A",
        "nodes": [
            {"node_id": "start", "node_type": "trigger", "name": "Start"},
            {"node_id": "end", "node_type": "action", "name": "End"},
        ],
        "edges": [{"edge_id": "e1", "source_node_id": "start", "target_node_id": "end"}],
    }


def test_workflow_create_update_and_publish(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_workspace_id] = _override_workspace_id
    app.dependency_overrides[workflow_routes.get_db_session] = _override_db

    async def _create_workflow(db, **kwargs):
        return SimpleNamespace(id=10)

    async def _get_workflow(db, workflow_id, workspace_id):
        return SimpleNamespace(
            id=workflow_id,
            workspace_id=workspace_id,
            name="Workflow A",
            description=None,
            status=WorkflowStatus.draft,
            definition={
                "nodes": _valid_workflow_payload()["nodes"],
                "edges": _valid_workflow_payload()["edges"],
            },
            version=1,
            created_by=1,
            created_at=datetime.now(timezone.utc),
            updated_at=datetime.now(timezone.utc),
            nodes=[],
            edges=[],
        )

    async def _update_workflow(db, workflow, **kwargs):
        return workflow

    monkeypatch.setattr(workflow_routes.workflow_service, "create_workflow", _create_workflow)
    monkeypatch.setattr(workflow_routes.workflow_service, "get_workflow_by_id", _get_workflow)
    monkeypatch.setattr(workflow_routes.workflow_service, "update_workflow", _update_workflow)

    create_resp = client.post("/workflows", json=_valid_workflow_payload())
    assert create_resp.status_code == 201

    update_resp = client.patch(
        "/workflows/10",
        json={"status": "published"},
    )
    assert update_resp.status_code == 200

    app.dependency_overrides.clear()


def test_workflow_graph_validation_errors(monkeypatch):
    client = TestClient(app)
    app.dependency_overrides[get_current_user] = _override_user
    app.dependency_overrides[get_workspace_id] = _override_workspace_id
    app.dependency_overrides[workflow_routes.get_db_session] = _override_db

    # malformed node payload
    malformed = {
        "name": "Bad",
        "nodes": [{"id": "n1", "name": "Missing type"}],
        "edges": [],
    }
    malformed_resp = client.post("/workflows", json=malformed)
    assert malformed_resp.status_code == 422

    # cyclic graph
    cyclic = {
        "name": "Cyclic",
        "nodes": [
            {"node_id": "a", "node_type": "trigger", "name": "A"},
            {"node_id": "b", "node_type": "action", "name": "B"},
        ],
        "edges": [
            {"edge_id": "e1", "source_node_id": "a", "target_node_id": "b"},
            {"edge_id": "e2", "source_node_id": "b", "target_node_id": "a"},
        ],
    }
    cyclic_resp = client.post("/workflows", json=cyclic)
    assert cyclic_resp.status_code == 422

    app.dependency_overrides.clear()
