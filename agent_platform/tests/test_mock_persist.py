"""Mock adapter disk persistence for US-3 restart simulation."""

from __future__ import annotations

from pathlib import Path

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.contracts import MemoryCategory, MemorySearchRequest, MemoryWriteRequest
from agent_platform.memory.service import MemoryService


def test_mock_persist_survives_new_service(tmp_path: Path) -> None:
    store = tmp_path / "store.json"
    cfg = {
        "backend": "mock",
        "device": {"default_id": "d1"},
        "mock": {"persist_path": str(store)},
    }
    svc1 = MemoryService(config=cfg)
    svc1.write("持久化测试", device_id="d1", category=MemoryCategory.preference)

    svc2 = MemoryService(config=cfg)
    res = svc2.search("持久化", device_id="d1")
    assert len(res.hits) == 1
