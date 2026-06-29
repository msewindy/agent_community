"""Phase 2 — AttemptService tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.attempt import AttemptService, compute_session_stats
from agent_platform.learning.contracts import AttemptRecord, utc_now
from agent_platform.learning.kp_catalog import GradeBoundaryError
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def ctx_svc(tmp_path: Path) -> StudentContextService:
    return StudentContextService(data_root=tmp_path / "student_data")


@pytest.fixture
def attempt_svc(ctx_svc: StudentContextService, tmp_path: Path) -> AttemptService:
    return AttemptService(data_root=tmp_path / "student_data", context_svc=ctx_svc)


@pytest.fixture
def student(ctx_svc: StudentContextService) -> str:
    sid = "s-attempt-1"
    ctx_svc.init_from_defaults(sid)
    return sid


def test_submit_correct(attempt_svc: AttemptService, student: str, tmp_path: Path) -> None:
    result = attempt_svc.submit(student, "q-g2m-001", "68")
    assert result.correct is True
    assert result.error_code is None
    path = tmp_path / "student_data" / student / "attempts" / f"{result.attempt_id}.json"
    assert path.is_file()


def test_submit_wrong_sets_error_code(attempt_svc: AttemptService, student: str) -> None:
    result = attempt_svc.submit(student, "q-g2m-002", "80")
    assert result.correct is False
    assert result.error_code == "CARRY_ERROR"


def test_attempts_today_increments(attempt_svc: AttemptService, student: str) -> None:
    attempt_svc.submit(student, "q-g2m-001", "68")
    attempt_svc.submit(student, "q-g2m-002", "85")
    ctx = attempt_svc._ctx.get(student)
    assert ctx.session_stats is not None
    assert ctx.session_stats.attempts_today == 2


def test_correct_rate_7d_mixed(attempt_svc: AttemptService, student: str) -> None:
    attempt_svc.submit(student, "q-g2m-001", "68")
    attempt_svc.submit(student, "q-g2m-002", "85")
    attempt_svc.submit(student, "q-g2m-003", "83")
    attempt_svc.submit(student, "q-g2m-004", "0")
    ctx = attempt_svc._ctx.get(student)
    assert ctx.session_stats is not None
    assert ctx.session_stats.correct_rate_7d == pytest.approx(0.75)


def test_submit_without_context_raises(attempt_svc: AttemptService) -> None:
    with pytest.raises(FileNotFoundError):
        attempt_svc.submit("missing", "q-g2m-001", "68")


def test_grade_boundary_blocks_over_grade_unit(
    ctx_svc: StudentContextService,
    tmp_path: Path,
) -> None:
    from agent_platform.learning.contracts import Curriculum, PipelineStage, StudentContextInit

    sid = "s-grade-boundary"
    ctx_svc.init(
        sid,
        StudentContextInit(
            curriculum=Curriculum(
                grade="一年级",
                grade_level=1,
                subject="数学",
                unit_id="math-g2-add-sub-100",
                unit_title="100以内加减法",
            ),
            pipeline_stage=PipelineStage.practice,
        ),
    )
    att = AttemptService(data_root=tmp_path / "student_data", context_svc=ctx_svc)
    with pytest.raises(ValueError, match="grade boundary"):
        att.submit(sid, "q-g2m-001", "68")


def test_compute_session_stats_empty() -> None:
    stats = compute_session_stats([])
    assert stats.attempts_today == 0
    assert stats.correct_rate_7d is None


def test_compute_session_stats_window() -> None:
    now = utc_now()
    attempts = [
        AttemptRecord(
            attempt_id="att-1",
            student_id="s1",
            question_id="q1",
            unit_id="u1",
            submitted_at=now,
            answer_raw="1",
            answer_normalized="1",
            correct=True,
            expected_answer="1",
            explanation="e",
            knowledge_point_id="kp1",
            trace_id="t1",
        ),
        AttemptRecord(
            attempt_id="att-2",
            student_id="s1",
            question_id="q2",
            unit_id="u1",
            submitted_at=now,
            answer_raw="2",
            answer_normalized="2",
            correct=False,
            expected_answer="1",
            explanation="e",
            knowledge_point_id="kp1",
            trace_id="t2",
        ),
    ]
    stats = compute_session_stats(attempts, now)
    assert stats.attempts_today == 2
    assert stats.correct_rate_7d == pytest.approx(0.5)
