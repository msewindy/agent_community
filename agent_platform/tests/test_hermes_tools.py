"""M2 D8 — Hermes agent_memory_* tool handlers."""

from __future__ import annotations

import json

import pytest

from agent_platform.integrations.hermes import tools as hermes_tools


@pytest.fixture
def svc():
    cfg = {
        "backend": "mock",
        "device": {"default_id": "hermes-test"},
        "gate": {"enabled": False},
        "audit": {"enabled": False},
    }
    from agent_platform.memory.service import MemoryService

    service = MemoryService(config=cfg)
    hermes_tools._get_service = lambda: service  # type: ignore[attr-defined]
    return service


def test_write_and_search(svc) -> None:
    out = json.loads(hermes_tools.agent_memory_write({"content": "喜欢简短回复", "category": "preference"}))
    assert out["success"]
    assert out["record_id"]

    search = json.loads(hermes_tools.agent_memory_search({"query": "简短"}))
    assert search["count"] >= 1


def test_trace_from_session(svc) -> None:
    out = json.loads(
        hermes_tools.agent_memory_write(
            {"content": "trace test"},
            current_session_id="sess-abc-123",
        )
    )
    assert out["success"]
    assert out["trace_id"].startswith("hermes-")


def test_delete(svc) -> None:
    out = json.loads(hermes_tools.agent_memory_write({"content": "to delete"}))
    rid = out["record_id"]
    del_out = json.loads(hermes_tools.agent_memory_delete({"record_id": rid}))
    assert del_out["success"]
    assert del_out["status"] == "tombstoned"
