"""P1-2 — learning unit API on student panel."""

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
def panel_with_student(tmp_path: Path) -> tuple[TestClient, str]:
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    ctx = StudentContextService(data_root=data)
    onboarding = OnboardingService(data_root=data, context_svc=ctx, catalog=catalog)
    sid = "g2-stu-test"
    ctx.init_from_defaults(sid, unit_id="math-g2-add-sub-100")
    onboarding.onboard(sid, grade_level=3, grade="三年级", active_unit_id="math-g2-add-sub-100")
    from agent_platform.learning.contracts import StudentContextPatch

    ctx.patch(
        sid,
        StudentContextPatch(
            curriculum=ctx.get(sid).curriculum.model_copy(update={"grade_level": 3})
        ),
    )
    cfg = {"data": {"root": str(data)}, "web_panel": {"port": 8770}, "pilot": {"grade_level": 3}}
    client = TestClient(create_app(config=cfg, catalog_svc=catalog, context_svc=ctx))
    return client, sid


def test_learning_unit_get_and_switch(panel_with_student) -> None:
    client, sid = panel_with_student
    snap = client.get(f"/api/students/{sid}/learning-unit")
    assert snap.status_code == 200
    body = snap.json()
    assert body["current"]["unit_id"] == "math-g2-add-sub-100"
    assert any(c["unit_id"] == "math-g3-u01" for c in body["choices"])

    switched = client.post(
        f"/api/students/{sid}/learning-unit",
        json={"unit_id": "math-g3-u01"},
    )
    assert switched.status_code == 200, switched.text
    result = switched.json()
    assert result["new_unit_id"] == "math-g3-u01"
    assert result["pipeline_stage"] == "learning"

    snap2 = client.get(f"/api/students/{sid}/learning-unit")
    assert snap2.json()["current"]["unit_id"] == "math-g3-u01"


def test_panel_shows_overview(panel_with_student) -> None:
    client, _ = panel_with_student
    page = client.get("/")
    assert page.status_code == 200
    assert "单元学习进度" in page.text
    assert "需关注" in page.text
    assert "统计周期" not in page.text
    assert "Jarvis 当前上下文" not in page.text

    detail = client.get("/learning-detail")
    assert detail.status_code == 200
    assert "知识点掌握" in detail.text
    assert "filterSubject" in detail.text
    assert "btnSetCurrent" not in detail.text

    exercises = client.get("/exercises")
    assert exercises.status_code == 200
    assert "待归类" in exercises.text
