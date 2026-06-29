"""M2 D3 — MockMemAdapter + MemoryPort compliance."""

from __future__ import annotations

import pytest

from agent_platform.memory.adapters.memverse import MemVerseAdapter
from agent_platform.memory.adapters.mock import MockMemAdapter, assert_implements_memory_port
from agent_platform.memory.contracts import (
    MemoryCategory,
    MemoryCorrectRequest,
    MemoryKind,
    MemorySearchRequest,
    MemoryStatus,
    MemoryWriteRequest,
)
from agent_platform.memory.gate import content_hash


@pytest.fixture
def adapter() -> MockMemAdapter:
    return MockMemAdapter()


def test_implements_memory_port(adapter: MockMemAdapter) -> None:
    assert_implements_memory_port(adapter)
    assert_implements_memory_port(MemVerseAdapter("http://127.0.0.1:8000"))


def test_write_and_get(adapter: MockMemAdapter) -> None:
    req = MemoryWriteRequest(
        content="用户偏好：简短回复",
        device_id="dev-a",
        category=MemoryCategory.preference,
        kind=MemoryKind.preference,
        trace_id="trace-1",
    )
    rec = adapter.write(req)
    assert rec.device_id == "dev-a"
    assert rec.category == MemoryCategory.preference
    assert rec.content_hash == content_hash(req.content)
    assert adapter.get(rec.record_id) == rec


def test_dedup_same_device_and_content(adapter: MockMemAdapter) -> None:
    req = MemoryWriteRequest(content="duplicate fact", device_id="dev-a")
    r1 = adapter.write(req)
    r2 = adapter.write(req)
    assert r1.record_id == r2.record_id
    assert len(adapter.all_records()) == 1


def test_dedup_disabled() -> None:
    ad = MockMemAdapter(dedup=False)
    req = MemoryWriteRequest(content="same", device_id="dev-a")
    r1 = ad.write(req)
    r2 = ad.write(req)
    assert r1.record_id != r2.record_id


def test_search_filters_device_and_category(adapter: MockMemAdapter) -> None:
    adapter.write(
        MemoryWriteRequest(content="项目 Alpha 里程碑", device_id="dev-a", category=MemoryCategory.project)
    )
    adapter.write(
        MemoryWriteRequest(content="喜欢简短", device_id="dev-b", category=MemoryCategory.preference)
    )

    hits_a = adapter.search(MemorySearchRequest(query="里程碑", device_id="dev-a"))
    assert len(hits_a.hits) == 1
    assert hits_a.hits[0].device_id == "dev-a"

    hits_pref = adapter.search(
        MemorySearchRequest(query="简短", device_id="dev-b", category=MemoryCategory.preference)
    )
    assert len(hits_pref.hits) == 1


def test_search_excludes_tombstoned(adapter: MockMemAdapter) -> None:
    rec = adapter.write(MemoryWriteRequest(content="旧偏好：冗长", device_id="dev-a"))
    adapter.correct(MemoryCorrectRequest(record_id=rec.record_id, reason="user fix"))
    res = adapter.search(MemorySearchRequest(query="冗长", device_id="dev-a"))
    assert len(res.hits) == 0
    assert adapter.get(rec.record_id).status == MemoryStatus.tombstoned


def test_search_tokenized_multi_word_query(adapter: MockMemAdapter) -> None:
    adapter.write(
        MemoryWriteRequest(
            content="用户偏好：回复风格简短直接",
            device_id="dev-a",
            category=MemoryCategory.preference,
        )
    )
    res = adapter.search(
        MemorySearchRequest(
            query="回复风格 偏好 reply style preference",
            device_id="dev-a",
        )
    )
    assert len(res.hits) == 1
    assert "简短" in res.hits[0].content


def test_correct_with_replacement_supersedes(adapter: MockMemAdapter) -> None:
    old = adapter.write(
        MemoryWriteRequest(
            content="旧偏好：冗长",
            device_id="dev-a",
            category=MemoryCategory.preference,
        )
    )
    new = adapter.correct(
        MemoryCorrectRequest(
            record_id=old.record_id,
            reason="prefer short",
            replacement=MemoryWriteRequest(
                content="新偏好：简短",
                device_id="dev-a",
                category=MemoryCategory.preference,
            ),
        )
    )
    assert new.record_id != old.record_id
    tomb = adapter.get(old.record_id)
    assert tomb is not None
    assert tomb.status == MemoryStatus.tombstoned
    assert tomb.supersedes == new.record_id

    assert len(adapter.search(MemorySearchRequest(query="冗长", device_id="dev-a")).hits) == 0
    assert len(adapter.search(MemorySearchRequest(query="简短", device_id="dev-a")).hits) == 1


def test_list_records_active_only(adapter: MockMemAdapter) -> None:
    r1 = adapter.write(MemoryWriteRequest(content="a", device_id="dev-a"))
    adapter.write(MemoryWriteRequest(content="b", device_id="dev-a"))
    adapter.correct(MemoryCorrectRequest(record_id=r1.record_id, reason="x"))
    listed = adapter.list_records(device_id="dev-a")
    assert len(listed) == 1
    assert listed[0].content == "b"


def test_correct_missing_record_raises(adapter: MockMemAdapter) -> None:
    with pytest.raises(KeyError, match="not found"):
        adapter.correct(MemoryCorrectRequest(record_id="missing", reason="x"))


def test_clear(adapter: MockMemAdapter) -> None:
    adapter.write(MemoryWriteRequest(content="x", device_id="dev-a"))
    adapter.clear()
    assert adapter.all_records() == []
