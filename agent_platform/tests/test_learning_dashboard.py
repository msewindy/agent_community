"""Learning dashboard API — dynamic subjects from catalog."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.student_panel import create_app
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.student_context import StudentContextService

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def dash_client(tmp_path: Path) -> tuple[TestClient, str]:
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    ctx = StudentContextService(data_root=data)
    onboarding = OnboardingService(data_root=data, context_svc=ctx, catalog=catalog)
    sid = "stu-dash"
    ctx.init_from_defaults(sid, unit_id="math-g3-u01")
    onboarding.onboard(sid, grade_level=3, grade="三年级", active_unit_id="math-g3-u01")
    cfg = {"data": {"root": str(data)}, "web_panel": {"port": 8770}, "pilot": {"grade_level": 3}}
    client = TestClient(create_app(config=cfg, catalog_svc=catalog, context_svc=ctx))
    return client, sid


def test_learning_dashboard_subjects_from_catalog(dash_client) -> None:
    client, sid = dash_client
    res = client.get(f"/api/students/{sid}/learning-dashboard")
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["student_id"] == sid
    assert body["grade_level"] == 3
    subjects = {s["subject"] for s in body["subjects"]}
    assert "数学" in subjects
    assert "语文" in subjects
    assert set(body["catalog_subjects"]) == subjects
    math = next(s for s in body["subjects"] if s["subject"] == "数学")
    assert math["units_total"] >= 1
    assert "units" in math
    assert "summary" in math
    assert "attention_items" in math


def test_learning_profile_unit_filter(dash_client) -> None:
    client, sid = dash_client
    res = client.get(
        f"/api/students/{sid}/learning-profile",
        params={"unit_id": "math-g3-u01", "include_pending": "false"},
    )
    assert res.status_code == 200
