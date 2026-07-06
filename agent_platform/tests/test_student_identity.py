"""Student display name from M2 user_profile."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_platform.learning.student_identity import (
    resolve_student_display_name,
    resolve_student_friendly_name,
    student_list_label,
)
from agent_platform.memory.contracts import MemoryCategory, MemoryKind, MemoryRecord, MemorySearchResult


def test_resolve_name_from_user_profile_list() -> None:
    mem = MagicMock()
    mem.default_device_id = "dev-1"
    mem.list_records.return_value = [
        MemoryRecord(
            record_id="r1",
            device_id="dev-1",
            category=MemoryCategory.user_profile,
            kind=MemoryKind.fact,
            content="孩子叫盈熙，今年8岁，上二年级。",
            content_hash="x",
            trace_id="t",
        )
    ]
    mem.search.return_value = MemorySearchResult(hits=[])
    name = resolve_student_display_name(
        "g2-stu-01",
        {"students": {"profiles": {"g2-stu-01": {"memory_device_id": "dev-1"}}}},
        memory_svc=mem,
    )
    assert name == "盈熙"


def test_resolve_name_fallback_to_config() -> None:
    mem = MagicMock()
    mem.list_records.side_effect = Exception("no mem")
    mem.search.side_effect = Exception("no mem")
    name = resolve_student_display_name(
        "g2-stu-01",
        {"students": {"profiles": {"g2-stu-01": {"preferred_name": "盈熙"}}}},
        memory_svc=mem,
    )
    assert name == "盈熙"


def test_resolve_name_fallback_to_student_id() -> None:
    mem = MagicMock()
    mem.default_device_id = "dev-1"
    mem.list_records.return_value = []
    mem.search.return_value = MemorySearchResult(hits=[])
    name = resolve_student_display_name("unknown-id", {}, memory_svc=mem)
    assert name == "unknown-id"


def test_resolve_friendly_name_none_when_only_id() -> None:
    mem = MagicMock()
    mem.list_records.return_value = []
    mem.search.return_value = MemorySearchResult(hits=[])
    assert resolve_student_friendly_name("unknown-stu-99", {}, memory_svc=mem) is None


def test_student_list_label_without_nickname() -> None:
    mem = MagicMock()
    mem.list_records.return_value = []
    mem.search.return_value = MemorySearchResult(hits=[])
    label = student_list_label("unknown-stu-99", {}, grade="三年级", memory_svc=mem)
    assert label == "未设置昵称（三年级）"


def test_extract_name_from_wo_shi() -> None:
    from agent_platform.learning.student_identity import _extract_name_from_text

    assert _extract_name_from_text("我是小明，三年级。") == "小明"
