#!/usr/bin/env python3
"""M2 D8 — smoke Hermes tool handlers without full Hermes CLI."""

from __future__ import annotations

import json
import sys

from agent_platform.integrations.hermes.tools import (
    agent_memory_delete,
    agent_memory_search,
    agent_memory_write,
    bootstrap_agent_platform,
)


def main() -> int:
    bootstrap_agent_platform()
    cfg = {
        "backend": "mock",
        "device": {"default_id": "hermes-smoke"},
        "gate": {"enabled": True, "dedup": True},
        "audit": {"enabled": True, "db_path": "/tmp/hermes_tool_smoke_audit.db"},
    }
    import os

    os.environ["AGENT_COMMUNITY_ROOT"] = str(bootstrap_agent_platform())

    # Patch service via env not easy — handlers use get_memory_service from config file
    # Use mock backend in memory.yaml or inject by writing temp - handlers call MemoryService() fresh each time
    from agent_platform.memory.service import MemoryService

    # Monkeypatch module-level for smoke only
    import agent_platform.integrations.hermes.tools as tools_mod

    svc = MemoryService(config=cfg)
    tools_mod._get_service = lambda: svc  # type: ignore[attr-defined]

    w = json.loads(agent_memory_write({"content": "Hermes 工具测试：偏好简短", "category": "preference"}))
    assert w.get("success"), w
    rid = w["record_id"]

    s = json.loads(agent_memory_search({"query": "简短"}))
    assert s.get("success") and s.get("count", 0) >= 1, s

    d = json.loads(agent_memory_delete({"record_id": rid}))
    assert d.get("success"), d

    s2 = json.loads(agent_memory_search({"query": "简短"}))
    assert s2.get("count", 0) == 0, s2

    print("smoke_hermes_tools: OK")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as e:
        print(f"smoke_hermes_tools: FAIL — {e}", file=sys.stderr)
        raise
