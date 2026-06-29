"""Phase 6 — study plan tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.contracts import LearningGoal, StudentContextPatch
from agent_platform.learning.remediation_skills import list_skill_ids, load_remediation_skills
from agent_platform.learning.study_plan import StudyPlanService
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "student_data"


@pytest.fixture
def ctx_svc(root: Path) -> StudentContextService:
    return StudentContextService(data_root=root)


@pytest.fixture
def student(ctx_svc: StudentContextService) -> str:
    sid = "plan-stu-1"
    ctx_svc.init_from_defaults(sid)
    return sid


def test_four_remediation_skills_loaded() -> None:
    skills = load_remediation_skills()
    assert len(skills) == 4
    assert "remediation/concept_v1" in list_skill_ids()


def test_generate_plan_sets_active_plan_id(
    ctx_svc: StudentContextService,
    root: Path,
    student: str,
) -> None:
    att = AttemptService(data_root=root, context_svc=ctx_svc)
    for _ in range(3):
        att.submit(student, "q-g2m-002", "80")

    plan_svc = StudyPlanService(data_root=root, ctx_svc=ctx_svc)
    plan = plan_svc.generate(student)
    assert 20 <= plan.duration_min <= 35
    assert plan.steps
    assert plan.skill_ids

    ctx = ctx_svc.get(student)
    assert ctx.focus.active_plan_id == plan.plan_id
