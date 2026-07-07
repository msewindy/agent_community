"""P1-2 — unit switch service."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.contracts import PipelineStage
from agent_platform.learning.kp_catalog import GradeBoundaryError, KpCatalogService
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.unit_switch import UnitSwitchService

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def unit_env(tmp_path: Path):
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    ctx = StudentContextService(data_root=data)
    onboarding = OnboardingService(data_root=data, context_svc=ctx, catalog=catalog)
    svc = UnitSwitchService(
        data_root=data,
        context_svc=ctx,
        catalog_svc=catalog,
        onboarding_svc=onboarding,
    )
    sid = "u-switch-1"
    ctx.init_from_defaults(sid, unit_id="math-g2-add-sub-100")
    onboarding.onboard(sid, grade="三年级", grade_level=3, active_unit_id="math-g2-add-sub-100")
    from agent_platform.learning.contracts import StudentContextPatch

    ctx.patch(
        sid,
        StudentContextPatch(
            curriculum=ctx.get(sid).curriculum.model_copy(update={"grade_level": 3})
        ),
    )
    return svc, ctx, sid, catalog


def test_get_snapshot_lists_grade_lte_units(unit_env) -> None:
    svc, _, sid, _ = unit_env
    snap = svc.get_snapshot(sid)
    assert snap.student_grade_level == 3
    assert snap.current.unit_id == "math-g2-add-sub-100"
    assert any(c.unit_id == "math-g3-u01" for c in snap.choices)
    assert all(c.grade <= 3 for c in snap.choices)


def test_switch_unit_updates_context_and_stage(unit_env) -> None:
    svc, ctx, sid, _ = unit_env
    result = svc.switch_active_unit(sid, "math-g3-u01")
    assert result.success is True
    assert result.previous_unit_id == "math-g2-add-sub-100"
    assert result.new_unit_id == "math-g3-u01"
    assert result.push_queue_size >= 0

    updated = ctx.get(sid)
    assert updated.curriculum.unit_id == "math-g3-u01"
    assert updated.pipeline_stage == PipelineStage.learning


def test_switch_same_unit_raises(unit_env) -> None:
    svc, _, sid, _ = unit_env
    with pytest.raises(ValueError, match="already on unit"):
        svc.switch_active_unit(sid, "math-g2-add-sub-100")


def test_grade_boundary_blocks(unit_env) -> None:
    svc, ctx, sid, _ = unit_env
    from agent_platform.learning.contracts import StudentContextPatch

    ctx.patch(
        sid,
        StudentContextPatch(
            curriculum=ctx.get(sid).curriculum.model_copy(update={"grade_level": 2})
        ),
    )
    with pytest.raises(GradeBoundaryError):
        svc.switch_active_unit(sid, "math-g3-u01")
