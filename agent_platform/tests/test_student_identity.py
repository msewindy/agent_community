"""Student display name from M2 user_profile."""

from __future__ import annotations

from unittest.mock import MagicMock

from agent_platform.learning.student_identity import resolve_student_display_name
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
