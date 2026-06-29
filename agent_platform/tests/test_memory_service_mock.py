"""M2 D3 — memory_service facade with MockMemAdapter (adapter swap isolation)."""

from __future__ import annotations

import pytest

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.contracts import MemoryCategory, MemoryCorrectRequest, MemoryWriteRequest
from agent_platform.memory.service import MemoryService, _build_adapter


def test_build_adapter_defaults_to_mock() -> None:
    ad = _build_adapter({"backend": "mock"})
    assert isinstance(ad, MockMemAdapter)


def test_service_write_search_us3_scenario(memory_service: MemoryService, device_id: str) -> None:
    """US-3 rehearsal: write preference → search recalls it."""
    rec = memory_service.write(
        "用户偏好：回复尽量简短",
        device_id=device_id,
        category=MemoryCategory.preference,
        trace_id="us3-trace",
    )
    assert rec.trace_id == "us3-trace"

    res = memory_service.search("简短", device_id=device_id)
    assert any("简短" in h.content for h in res.hits)

    listed = memory_service.list_records(device_id=device_id, category=MemoryCategory.preference)
    assert any(r.record_id == rec.record_id for r in listed)


def test_service_correct_via_facade(memory_service: MemoryService, device_id: str) -> None:
    old = memory_service.write("旧事实：周二开会", device_id=device_id)
    memory_service.correct(
        MemoryCorrectRequest(
            record_id=old.record_id,
            reason="wrong day",
            replacement=MemoryWriteRequest(
                content="新事实：周三开会",
                device_id=device_id,
            ),
        )
    )
    res = memory_service.search("周二", device_id=device_id)
    assert len(res.hits) == 0
    res2 = memory_service.search("周三", device_id=device_id)
    assert len(res2.hits) >= 1


def test_service_rejects_whitespace_content(mock_adapter: MockMemAdapter) -> None:
    """Pydantic 在 gate 之前校验 content（D5 可调整顺序）。"""
    from pydantic import ValidationError

    svc = MemoryService(
        adapter=mock_adapter,
        config={"device": {"default_id": "d"}, "gate": {"enabled": True}},
    )
    with pytest.raises(ValidationError):
        svc.write("   ", device_id="d")
