"""M2 D7 — memory panel API (US-7)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.memory_panel import create_app
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService


@pytest.fixture
def panel_client(tmp_path) -> TestClient:
    db = tmp_path / "panel_audit.db"
    cfg = {
        "backend": "mock",
        "device": {"default_id": "panel-test"},
        "gate": {"enabled": False},
        "audit": {"enabled": True, "db_path": str(db)},
        "panel": {"force_mock_backend": True, "enable_audit": True},
    }
    svc = MemoryService(config=cfg)
    app = create_app(config=cfg, service=svc)
    return TestClient(app)


def test_health_and_panel_html(panel_client: TestClient) -> None:
    r = panel_client.get("/health")
    assert r.status_code == 200
    assert r.json()["backend"] == "mock"

    html = panel_client.get("/")
    assert html.status_code == 200
    assert "记忆面板" in html.text


def test_list_filter_and_delete_us7(panel_client: TestClient) -> None:
    # Pre-seed service shared with panel app
    cfg = {
        "backend": "mock",
        "device": {"default_id": "dev-panel"},
        "gate": {"enabled": False},
        "audit": {"enabled": False},
        "panel": {"force_mock_backend": True},
    }
    svc = MemoryService(config=cfg)
    svc.write("偏好 A", device_id="dev-panel", category=MemoryCategory.preference)
    svc.write("项目 B", device_id="dev-panel", category=MemoryCategory.project)
    client = TestClient(create_app(config=cfg, service=svc))

    all_rows = client.get("/api/memories", params={"device_id": "dev-panel"}).json()
    assert len(all_rows) == 2

    pref = client.get(
        "/api/memories", params={"device_id": "dev-panel", "category": "preference"}
    ).json()
    assert len(pref) == 1
    rid = pref[0]["record_id"]

    del_r = client.delete(f"/api/memories/{rid}")
    assert del_r.status_code == 200
    assert del_r.json()["status"] == "tombstoned"

    after = client.get(
        "/api/memories", params={"device_id": "dev-panel", "category": "preference"}
    ).json()
    assert len(after) == 0

    search_scope = client.get("/api/memories", params={"device_id": "dev-panel"}).json()
    assert len(search_scope) == 1


def test_delete_404(panel_client: TestClient) -> None:
    r = panel_client.delete("/api/memories/does-not-exist")
    assert r.status_code == 404
