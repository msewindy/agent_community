"""Phase 6 — learning proactive tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.contracts import ContextFlags, LearningProactiveEventType, StudentContextPatch
from agent_platform.learning.learning_proactive import LearningProactiveService
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "student_data"


@pytest.fixture
def ctx_svc(root: Path) -> StudentContextService:
    return StudentContextService(data_root=root)


@pytest.fixture
def student(ctx_svc: StudentContextService) -> str:
    sid = "pro-stu-1"
    ctx_svc.init_from_defaults(sid)
    return sid


def test_attempt_summary_after_submit(
    ctx_svc: StudentContextService,
    root: Path,
    student: str,
) -> None:
    att = AttemptService(data_root=root, context_svc=ctx_svc)
    result = att.submit(student, "q-g2m-001", "68")
    assert result.proactive
    assert result.proactive[0].event_type == LearningProactiveEventType.attempt_summary
    assert result.proactive[0].delivered is True

    pro = LearningProactiveService(data_root=root, ctx_svc=ctx_svc)
    logged = pro.list_messages(student)
    assert any(m.event_type == LearningProactiveEventType.attempt_summary for m in logged)


def test_gap_recurrence_on_third_wrong(
    ctx_svc: StudentContextService,
    root: Path,
    student: str,
) -> None:
    att = AttemptService(data_root=root, context_svc=ctx_svc)
    for _ in range(3):
        result = att.submit(student, "q-g2m-002", "80")
    types = [m.event_type for m in result.proactive]
    assert LearningProactiveEventType.gap_recurrence in types


def test_dnd_suppresses_delivery(
    ctx_svc: StudentContextService,
    root: Path,
    student: str,
) -> None:
    ctx_svc.patch(student, StudentContextPatch(flags=ContextFlags(do_not_disturb=True)))
    att = AttemptService(data_root=root, context_svc=ctx_svc)
    result = att.submit(student, "q-g2m-001", "68")
    assert result.proactive[0].suppressed is True
    assert result.proactive[0].delivered is False
