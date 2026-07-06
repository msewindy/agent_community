"""Tests for L0 profile completeness assessment."""

from __future__ import annotations

from agent_platform.memory.contracts import MemoryCategory, MemoryKind, MemoryRecord
from agent_platform.memory.profile_completeness import assess_profile


def _rec(content: str, *, category=MemoryCategory.user_profile) -> MemoryRecord:
    return MemoryRecord(
        record_id="r1",
        device_id="dev-1",
        ts="2026-01-01T00:00:00Z",
        category=category,
        kind=MemoryKind.fact,
        content=content,
        content_hash="abc",
    )


class _FakeMemory:
    def __init__(self, records):
        self._records = records
        self.default_device_id = "dev-1"

    def list_records(self, **kwargs):
        return list(self._records)


def test_assess_empty_profile() -> None:
    snap = assess_profile(memory_svc=_FakeMemory([]))
    assert not snap.is_complete
    assert snap.missing == ["name", "grade", "interest"]


def test_assess_with_onboarding_grade_and_name_in_memory() -> None:
    snap = assess_profile(
        memory_svc=_FakeMemory([_rec("孩子叫小明，今年8岁。")]),
        onboarding_grade="三年级",
    )
    assert snap.has_display_name
    assert snap.display_name == "小明"
    assert snap.has_grade_hint
    assert snap.missing == ["interest"]


def test_assess_interest_from_preference() -> None:
    snap = assess_profile(
        memory_svc=_FakeMemory(
            [
                _rec("孩子叫小红。", category=MemoryCategory.user_profile),
                _rec("喜欢画画和跳舞", category=MemoryCategory.preference),
            ]
        ),
        onboarding_grade="三年级",
    )
    assert snap.is_complete
