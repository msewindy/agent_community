"""Phase 4 — PushEngine tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.push_engine import PushEngineService, build_push_queue, dominant_gap_id
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "student_data"


@pytest.fixture
def ctx_svc(root: Path) -> StudentContextService:
    return StudentContextService(data_root=root)


@pytest.fixture
def bank() -> QuestionBankService:
    return QuestionBankService()


@pytest.fixture
def push_svc(ctx_svc: StudentContextService, root: Path, bank: QuestionBankService) -> PushEngineService:
    return PushEngineService(data_root=root, bank=bank, context_svc=ctx_svc)


@pytest.fixture
def attempt_svc(
    ctx_svc: StudentContextService,
    root: Path,
    bank: QuestionBankService,
    push_svc: PushEngineService,
) -> AttemptService:
    return AttemptService(
        data_root=root,
        context_svc=ctx_svc,
        question_bank=bank,
        push_engine=push_svc,
    )


@pytest.fixture
def student(ctx_svc: StudentContextService) -> str:
    sid = "push-stu-1"
    ctx_svc.init_from_defaults(sid)
    return sid


def test_active_gap_queue_targets_gap_kp(
    attempt_svc: AttemptService,
    push_svc: PushEngineService,
    student: str,
) -> None:
    for _ in range(3):
        attempt_svc.submit(student, "q-g2m-002", "80")

    queue = push_svc.get_queue(student)
    dom = dominant_gap_id(queue)
    assert dom == "gap-kp-g2-add-carry"
    remediation = [i for i in queue.items if i.gap_id == "gap-kp-g2-add-carry"]
    assert remediation


def test_mastered_gap_no_longer_dominant(
    attempt_svc: AttemptService,
    push_svc: PushEngineService,
    student: str,
) -> None:
    for _ in range(3):
        attempt_svc.submit(student, "q-g2m-002", "80")
    attempt_svc.submit(student, "q-g2m-002", "85")
    attempt_svc.submit(student, "q-g2m-003", "83")
    attempt_svc.submit(student, "q-g2m-009", "75")

    attempt_svc.submit(student, "q-g2m-005", "30")
    queue = push_svc.get_queue(student)
    dom = dominant_gap_id(queue)
    assert dom == "gap-kp-g2-sub-borrow"
    assert dom != "gap-kp-g2-add-carry"


def test_fetch_returns_batch(
    attempt_svc: AttemptService,
    push_svc: PushEngineService,
    student: str,
) -> None:
    attempt_svc.submit(student, "q-g2m-002", "80")
    result = push_svc.fetch(student, count=3)
    assert 1 <= len(result.questions) <= 3
    assert result.question_ids


def test_rebuild_syncs_focus_queue_head(
    attempt_svc: AttemptService,
    ctx_svc: StudentContextService,
    student: str,
) -> None:
    attempt_svc.submit(student, "q-g2m-002", "80")
    ctx = ctx_svc.get(student)
    assert ctx.focus.queue_head_question_ids


def test_build_queue_unit_practice_without_gaps(
    bank: QuestionBankService,
    student: str,
) -> None:
    from agent_platform.learning.contracts import GapMap, utc_now

    gap_map = GapMap(
        student_id=student,
        updated_at=utc_now(),
        unit_id="math-g2-add-sub-100",
        gaps=[],
    )
    queue = build_push_queue(
        student_id=student,
        unit_id="math-g2-add-sub-100",
        gap_map=gap_map,
        bank=bank,
        attempts=[],
    )
    assert queue.items
    assert all(i.reason.value == "unit_practice" for i in queue.items[:3])
