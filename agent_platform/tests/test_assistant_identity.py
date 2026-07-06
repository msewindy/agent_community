"""Tests for assistant display name resolution."""

from __future__ import annotations

from agent_platform.memory.assistant_identity import (
    ASSISTANT_ALIAS_SUBJECT_KEY,
    DEFAULT_ASSISTANT_NAME,
    resolve_assistant_display_name,
)
from agent_platform.memory.contracts import MemoryCategory, MemoryKind, MemoryRecord


def _rec(content: str, *, meta=None) -> MemoryRecord:
    return MemoryRecord(
        record_id="r1",
        device_id="dev-1",
        ts="2026-01-01T00:00:00Z",
        category=MemoryCategory.preference,
        kind=MemoryKind.fact,
        content=content,
        content_hash="abc",
        metadata=meta or {},
    )


class _FakeMemory:
    def __init__(self, records):
        self._records = records
        self.default_device_id = "dev-1"

    def list_records(self, **kwargs):
        return list(self._records)


def test_default_assistant_name() -> None:
    assert resolve_assistant_display_name(memory_svc=_FakeMemory([])) == DEFAULT_ASSISTANT_NAME


def test_alias_from_subject_key_metadata() -> None:
    snap = resolve_assistant_display_name(
        memory_svc=_FakeMemory(
            [
                _rec(
                    "助手别名：豆豆",
                    meta={"subject_key": ASSISTANT_ALIAS_SUBJECT_KEY},
                )
            ]
        )
    )
    assert snap == "豆豆"


def test_alias_from_natural_language() -> None:
    snap = resolve_assistant_display_name(
        memory_svc=_FakeMemory([_rec("以后叫你阿宝")])
    )
    assert snap == "阿宝"
