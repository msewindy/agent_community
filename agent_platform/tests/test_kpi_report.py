"""Phase 7 — KPI report tests."""

from __future__ import annotations

from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.kpi_report import LearningKpiService
from agent_platform.learning.seed_manifest import verify_seed_package
from agent_platform.learning.student_context import StudentContextService


def test_seed_verify_passes() -> None:
    result = verify_seed_package()
    assert result.ok
    assert result.question_count >= 10
    assert result.taxonomy_count >= 5


def test_kpi_report_after_attempts(tmp_path: Path) -> None:
    root = tmp_path / "student_data"
    ctx_svc = StudentContextService(data_root=root)
    sid = "kpi-stu-1"
    ctx_svc.init_from_defaults(sid)
    att = AttemptService(data_root=root, context_svc=ctx_svc)
    att.submit(sid, "q-g2m-001", "68")
    att.submit(sid, "q-g2m-002", "80")

    report = LearningKpiService(data_root=root).build_report(sid, period_days=90)
    assert report.attempts_total == 2
    assert report.correct_rate == 0.5
