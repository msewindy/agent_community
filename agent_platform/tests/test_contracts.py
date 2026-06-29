"""M2 D2 — memory contract schema tests."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest
from pydantic import ValidationError

from agent_platform.memory.contracts import (
    SCHEMA_MODELS,
    SCHEMA_VERSION,
    GateDecision,
    MemoryCategory,
    MemoryCorrectRequest,
    MemoryHit,
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    MemoryStatus,
    MemoryWriteRequest,
    ObserveEvent,
    ObserveSource,
    export_json_schemas,
    write_json_schemas,
)


def test_memory_record_required_fields():
    rec = MemoryRecord(
        device_id="reachy-desktop-01",
        category=MemoryCategory.preference,
        content="用户偏好：回复简短",
    )
    assert rec.device_id == "reachy-desktop-01"
    assert rec.category == MemoryCategory.preference
    assert rec.ts.tzinfo is not None
    assert rec.is_active
    assert rec.status == MemoryStatus.active


def test_memory_record_from_write_request():
    req = MemoryWriteRequest(
        content="  hello world  ",
        device_id="d1",
        category=MemoryCategory.project,
        kind=MemoryKind.fact,
        trace_id="trace-abc",
    )
    rec = MemoryRecord.from_write_request(req, record_id="fixed-id")
    assert rec.record_id == "fixed-id"
    assert rec.content == "hello world"
    assert rec.category == MemoryCategory.project
    assert rec.trace_id == "trace-abc"


def test_memory_record_tombstone_and_supersede():
    rec = MemoryRecord(device_id="d1", content="old fact")
    tomb = rec.as_tombstone(reason="user correction")
    assert tomb.status == MemoryStatus.tombstoned
    assert tomb.metadata["tombstone_reason"] == "user correction"

    superseded = rec.as_superseded_by("new-id")
    assert superseded.supersedes == "new-id"
    assert superseded.status == MemoryStatus.tombstoned


def test_write_request_rejects_empty_content():
    with pytest.raises(ValidationError):
        MemoryWriteRequest(content="   ", device_id="d1")


def test_write_request_rejects_empty_device_id():
    with pytest.raises(ValidationError):
        MemoryWriteRequest(content="ok", device_id="")


def test_search_request_limit_bounds():
    MemorySearchRequest(query="x", limit=1)
    MemorySearchRequest(query="x", limit=100)
    with pytest.raises(ValidationError):
        MemorySearchRequest(query="x", limit=0)
    with pytest.raises(ValidationError):
        MemorySearchRequest(query="x", limit=101)


def test_observe_event_requires_text_or_payload():
    with pytest.raises(ValidationError):
        ObserveEvent(source=ObserveSource.voice)
    ev = ObserveEvent(text="用户说：明天开会", source=ObserveSource.voice)
    assert ev.modality == ["text"]
    assert ev.trace_id


def test_observe_event_to_write_request():
    ev = ObserveEvent(
        text="偏好简短回复",
        device_id="reachy-01",
        source=ObserveSource.chat,
        trace_id="t-1",
    )
    req = ev.to_write_request(device_id="fallback", category=MemoryCategory.preference)
    assert req.device_id == "reachy-01"
    assert req.category == MemoryCategory.preference
    assert req.source_event_id == ev.event_id
    assert req.metadata["source"] == "chat"


def test_observe_event_payload_json():
    ev = ObserveEvent(payload={"intent": "reminder", "when": "tomorrow"})
    req = ev.to_write_request(device_id="d1")
    assert "reminder" in req.content


def test_json_round_trip_memory_record():
    rec = MemoryRecord(
        device_id="d1",
        content="fact",
        ts=datetime(2026, 5, 21, 12, 0, 0, tzinfo=timezone.utc),
    )
    data = rec.model_dump(mode="json")
    restored = MemoryRecord.model_validate(data)
    assert restored.record_id == rec.record_id
    assert restored.ts == rec.ts


def test_export_json_schemas_bundle():
    bundle = export_json_schemas()
    assert bundle["version"] == SCHEMA_VERSION
    defs = bundle["definitions"]
    for model in SCHEMA_MODELS:
        assert model.__name__ in defs
        assert "$defs" in defs[model.__name__] or "properties" in defs[model.__name__]


def test_write_json_schemas_file(tmp_path: Path):
    out = tmp_path / "memory_bundle.json"
    write_json_schemas(out)
    loaded = json.loads(out.read_text(encoding="utf-8"))
    assert "MemoryRecord" in loaded["definitions"]


def test_gate_decision_extra_forbid():
    GateDecision(allowed=True)
    with pytest.raises(ValidationError):
        GateDecision(allowed=True, unknown_field=1)  # type: ignore[call-arg]


def test_memory_hit_score_bounds():
    MemoryHit(record_id="1", content="x", score=0.5)
    with pytest.raises(ValidationError):
        MemoryHit(record_id="1", content="x", score=1.5)


def test_memory_correct_request_minimal():
    req = MemoryCorrectRequest(record_id="rid-1", reason="wrong date")
    assert req.replacement is None
