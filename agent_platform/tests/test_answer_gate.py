"""Phase 5 — AnswerGate tests."""

from __future__ import annotations

from agent_platform.learning.answer_gate import StudentAnswerGate
from agent_platform.learning.contracts import (
    GapEntry,
    GapMastery,
    GapStats,
    GapStatus,
    utc_now,
)


def _gap(gap_id: str, **kwargs) -> GapEntry:
    now = utc_now()
    base = dict(
        gap_id=gap_id,
        error_code="CARRY_ERROR",
        knowledge_point_id="kp-g2-add-carry",
        title="进位错误",
        status=GapStatus.active,
        stats=GapStats(wrong_7d=3, total_wrong=3, total_attempts=3, last_wrong_at=now),
        mastery=GapMastery(required_streak=3),
        last_seen_at=now,
    )
    base.update(kwargs)
    return GapEntry.model_validate(base)


def test_blocks_repeated_error_without_evidence() -> None:
    gate = StudentAnswerGate()
    result = gate.check("你反复在进位计算这个点出错。", gaps=[])
    assert result.passed is False
    assert result.rewritten is True
    assert "反复" not in result.text or "先不直接" in result.text


def test_passes_with_gap_id_and_data() -> None:
    gate = StudentAnswerGate()
    gaps = [_gap("gap-carry-error")]
    text = "根据 gap-carry-error，你近期在进位错误上有 3 次错误。"
    result = gate.check(text, gaps)
    assert result.passed is True
    assert result.rewritten is False


def test_passes_neutral_text() -> None:
    gate = StudentAnswerGate()
    result = gate.check("我们先看下一题的加减法步骤。", gaps=[])
    assert result.passed is True
