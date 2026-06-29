"""M2 D6 — audit store and trace_id correlation."""

from __future__ import annotations

import pytest

from agent_platform.memory.audit import AuditEvent, AuditStore, load_audit_config
from agent_platform.memory.contracts import MemoryCategory, MemoryCorrectRequest, MemoryWriteRequest
from agent_platform.memory.service import MemoryService
from agent_platform.memory.trace import new_trace_id, trace_from_session


def test_audit_store_append_and_query(tmp_path) -> None:
    db = tmp_path / "audit.db"
    store = AuditStore(db)
    store.append(
        AuditEvent(trace_id="t1", event_type="write", outcome="ok", device_id="d1", record_id="r1")
    )
    store.append(
        AuditEvent(trace_id="t1", event_type="search", outcome="ok", payload={"hit_count": 2})
    )
    store.append(AuditEvent(trace_id="t2", event_type="write", outcome="ok"))

    rows = store.list_by_trace("t1")
    assert len(rows) == 2
    assert rows[0]["event_type"] == "write"
    assert rows[1]["payload"]["hit_count"] == 2


def test_service_audit_chain_on_write_and_gate_reject(tmp_path) -> None:
    db = tmp_path / "svc_audit.db"
    cfg = {
        "backend": "mock",
        "device": {"default_id": "dev-audit"},
        "gate": {"enabled": True, "dedup": True},
        "audit": {"enabled": True, "db_path": str(db)},
    }
    svc = MemoryService(config=cfg)
    tid = "trace-d6-001"

    svc.write("唯一记忆", device_id="dev-audit", trace_id=tid)
    with pytest.raises(PermissionError):
        svc.write("唯一记忆", device_id="dev-audit", trace_id=tid)

    chain = svc.audit_trace(tid)
    types = [e["event_type"] for e in chain]
    assert "write_request" in types
    assert "write" in types
    assert any(e["event_type"] == "gate_evaluate" and e["outcome"] == "rejected" for e in chain)


def test_service_search_audit(tmp_path) -> None:
    db = tmp_path / "search_audit.db"
    svc = MemoryService(
        config={
            "backend": "mock",
            "audit": {"enabled": True, "db_path": str(db)},
        }
    )
    tid = new_trace_id()
    svc.write("searchable fact", trace_id=tid)
    svc.search("searchable", trace_id=tid)
    chain = svc.audit_trace(tid)
    assert any(e["event_type"] == "search" for e in chain)


def test_service_correct_audit(tmp_path) -> None:
    db = tmp_path / "correct_audit.db"
    svc = MemoryService(
        config={
            "backend": "mock",
            "audit": {"enabled": True, "db_path": str(db)},
        }
    )
    tid = new_trace_id()
    old = svc.write("old", trace_id=tid)
    svc.correct(
        MemoryCorrectRequest(
            record_id=old.record_id,
            reason="fix",
            trace_id=tid,
            replacement=MemoryWriteRequest(content="new", device_id=old.device_id),
        )
    )
    chain = svc.audit_trace(tid)
    assert any(e["event_type"] == "correct" for e in chain)


def test_load_audit_config() -> None:
    cfg = load_audit_config({"audit": {"enabled": True, "db_path": "/tmp/x.db"}})
    assert cfg.enabled
    assert cfg.db_path == "/tmp/x.db"


def test_trace_from_session() -> None:
    assert trace_from_session("abc").startswith("hermes-")
    assert trace_from_session("trace:uuid-1") == "uuid-1"
