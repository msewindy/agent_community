#!/usr/bin/env python3
"""M2 D7 — quick panel API smoke without starting uvicorn server."""

from __future__ import annotations

import sys

from fastapi.testclient import TestClient

from agent_platform.api.memory_panel import create_app
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService


def main() -> int:
    cfg = {
        "backend": "mock",
        "device": {"default_id": "smoke-panel"},
        "gate": {"enabled": True, "dedup": True},
        "audit": {"enabled": True, "db_path": "/tmp/agent_panel_smoke_audit.db"},
        "panel": {"force_mock_backend": True, "enable_audit": True},
    }
    svc = MemoryService(config=cfg)
    svc.write("面板测试记忆", device_id="smoke-panel", category=MemoryCategory.preference)
    client = TestClient(create_app(config=cfg, service=svc))

    rows = client.get("/api/memories", params={"device_id": "smoke-panel"}).json()
    if not rows:
        print("smoke_panel: FAIL no rows", file=sys.stderr)
        return 1
    rid = rows[0]["record_id"]
    client.delete(f"/api/memories/{rid}")
    after = client.get("/api/memories", params={"device_id": "smoke-panel"}).json()
    if after:
        print("smoke_panel: FAIL still listed after delete", file=sys.stderr)
        return 1
    print("smoke_panel: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
