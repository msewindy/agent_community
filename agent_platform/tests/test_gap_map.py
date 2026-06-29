"""Phase 3 — GapMap tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.contracts import GapStatus
from agent_platform.learning.gap_map import GapMapService, GapMapUpdater, top_gap_ids
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def root(tmp_path: Path) -> Path:
    return tmp_path / "student_data"


@pytest.fixture
def ctx_svc(root: Path) -> StudentContextService:
    return StudentContextService(data_root=root)


@pytest.fixture
def attempt_svc(ctx_svc: StudentContextService, root: Path) -> AttemptService:
    return AttemptService(data_root=root, context_svc=ctx_svc)


@pytest.fixture
def gap_svc(root: Path) -> GapMapService:
    return GapMapService(data_root=root)


@pytest.fixture
def student(ctx_svc: StudentContextService) -> str:
    sid = "gap-stu-1"
    ctx_svc.init_from_defaults(sid)
    return sid


def test_empty_gap_map_before_attempts(gap_svc: GapMapService, student: str) -> None:
    gaps = gap_svc.query(student)
    assert gaps == []


def test_same_error_three_times_wrong_7d(
    attempt_svc: AttemptService,
    gap_svc: GapMapService,
    student: str,
) -> None:
    for _ in range(3):
        attempt_svc.submit(student, "q-g2m-002", "80")

    gap = gap_svc.get_gap(student, "gap-kp-g2-add-carry")
    assert gap.stats.wrong_7d == 3
    assert gap.stats.total_wrong == 3
    assert gap.status == GapStatus.active
    assert gap.error_breakdown.get("CARRY_ERROR") == 3


def test_three_correct_after_wrong_masters_gap(
    attempt_svc: AttemptService,
    gap_svc: GapMapService,
    ctx_svc: StudentContextService,
    student: str,
) -> None:
    for _ in range(3):
        attempt_svc.submit(student, "q-g2m-002", "80")

    attempt_svc.submit(student, "q-g2m-002", "85")
    attempt_svc.submit(student, "q-g2m-003", "83")
    attempt_svc.submit(student, "q-g2m-009", "75")

    gap = gap_svc.get_gap(student, "gap-kp-g2-add-carry")
    assert gap.status == GapStatus.mastered
    assert gap.mastery.streak_correct >= 3
    assert gap.mastery.mastered_at is not None

    ctx = ctx_svc.get(student)
    assert "gap-kp-g2-add-carry" not in ctx.focus.top_gap_ids


def test_top_gap_ids_excludes_mastered() -> None:
    from agent_platform.learning.contracts import (
        GapEntry,
        GapMastery,
        GapStats,
        utc_now,
    )

    now = utc_now()
    active = GapEntry(
        gap_id="gap-a",
        error_code="A",
        knowledge_point_id="kp1",
        title="a",
        status=GapStatus.active,
        stats=GapStats(wrong_7d=2, total_wrong=2, total_attempts=2, last_wrong_at=now),
        mastery=GapMastery(required_streak=3),
        last_seen_at=now,
    )
    mastered = GapEntry(
        gap_id="gap-b",
        error_code="B",
        knowledge_point_id="kp1",
        title="b",
        status=GapStatus.mastered,
        stats=GapStats(wrong_7d=0, total_wrong=1, total_attempts=4, last_wrong_at=now),
        mastery=GapMastery(required_streak=3, streak_correct=3, mastered_at=now),
        last_seen_at=now,
    )
    tops = top_gap_ids([active, mastered])
    assert tops == ["gap-a"]


def test_rebuild_evidence_attempt_ids(
    ctx_svc: StudentContextService,
    root: Path,
    student: str,
) -> None:
    attempt_svc = AttemptService(data_root=root, context_svc=ctx_svc)
    ids = []
    for _ in range(2):
        r = attempt_svc.submit(student, "q-g2m-002", "80")
        ids.append(r.attempt_id)

    gap_svc = GapMapService(data_root=root)
    gap = gap_svc.get_gap(student, "gap-kp-g2-add-carry")
    assert gap.evidence_attempt_ids[0] == ids[-1]
    assert ids[-1] in gap.evidence_attempt_ids
