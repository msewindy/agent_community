"""M2 D5 — memory gate (dedup, conflict, sensitive)."""

from __future__ import annotations

import pytest

from agent_platform.memory.contracts import MemoryCategory, MemoryKind, MemoryRecord, MemoryWriteRequest
from agent_platform.memory.gate import (
    GateConfig,
    apply_write_metadata,
    content_hash,
    evaluate_write,
    load_gate_config,
    subject_key,
)
from agent_platform.memory.service import MemoryService


def test_content_hash_stable() -> None:
    assert content_hash("a  b") == content_hash("a b")


def test_subject_key_from_metadata() -> None:
    req = MemoryWriteRequest(
        content="x",
        device_id="d",
        metadata={"subject_key": "meeting.day"},
    )
    assert subject_key(req) == "meeting.day"


def test_duplicate_rejected() -> None:
    existing = [
        MemoryRecord(
            device_id="d",
            content="same",
            content_hash=content_hash("same"),
            category=MemoryCategory.other,
        )
    ]
    req = MemoryWriteRequest(content="same", device_id="d")
    d = evaluate_write(req, enabled=True, existing=existing, config=GateConfig(enabled=True))
    assert not d.allowed
    assert d.reason_code == "duplicate"


def test_conflict_rejected() -> None:
    existing = [
        MemoryRecord(
            device_id="d",
            content="周二开会",
            content_hash=content_hash("周二开会"),
            category=MemoryCategory.project,
            metadata={"subject_key": "meeting.day"},
        )
    ]
    req = MemoryWriteRequest(
        content="周三开会",
        device_id="d",
        category=MemoryCategory.project,
        metadata={"subject_key": "meeting.day"},
    )
    d = evaluate_write(req, enabled=True, existing=existing, config=GateConfig(enabled=True))
    assert not d.allowed
    assert d.reason_code == "conflict"


def test_sensitive_keyword() -> None:
    req = MemoryWriteRequest(content="here is my password", device_id="d")
    cfg = GateConfig(enabled=True, sensitive_keywords=["password"])
    d = evaluate_write(req, enabled=True, config=cfg)
    assert not d.allowed
    assert d.reason_code == "sensitive_keyword"


def test_apply_write_metadata() -> None:
    req = MemoryWriteRequest(content="fact", device_id="d")
    out = apply_write_metadata(req, evaluate_write(req, enabled=False))
    assert out.metadata["subject_key"]
    assert out.metadata["content_hash"]
    assert out.metadata["source_tier"] == "user_explicit"


def test_load_gate_config() -> None:
    cfg = load_gate_config(
        {
            "gate": {
                "enabled": True,
                "sensitive_keywords": ["token"],
            }
        }
    )
    assert cfg.enabled
    assert "token" in cfg.sensitive_keywords


def test_service_gate_duplicate_via_facade() -> None:
    svc = MemoryService(
        config={
            "backend": "mock",
            "device": {"default_id": "g-d5"},
            "gate": {"enabled": True, "dedup": True, "conflict_check": True},
        }
    )
    svc.write("唯一事实 A", device_id="g-d5")
    with pytest.raises(PermissionError, match="duplicate"):
        svc.write("唯一事实 A", device_id="g-d5")
