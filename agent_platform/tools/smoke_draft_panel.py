#!/usr/bin/env python3
"""M6 D4 smoke — draft panel API (TestClient, no uvicorn)."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def run_smoke() -> int:
    from fastapi.testclient import TestClient

    from agent_platform.api.draft_panel import create_app
    from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus
    from agent_platform.tools.service import ToolService

    with tempfile.TemporaryDirectory(prefix="draft-panel-") as td:
        root = Path(td) / "store"
        sandbox = Path(td) / "sandbox"
        sandbox.mkdir()
        cfg = {
            "enabled": True,
            "sandbox": {"root": str(sandbox), "auto_init": False},
            "governance": {
                "tool_levels": {
                    "filesystem.read_file": "L0",
                    "filesystem.write_file": "L2",
                }
            },
            "draft_gate": {"enabled": True},
            "store": {"root": str(root)},
            "servers": {
                "filesystem": {"enabled": True, "transport": "mock"},
                "fetch": {"enabled": False},
            },
            "panel": {"force_mock_transports": True},
        }
        svc = ToolService(config=cfg, store_root=root, sandbox_root=sandbox)
        client = TestClient(create_app(config=cfg, service=svc))

        health = client.get("/health")
        if health.status_code != 200:
            print("FAIL health", file=sys.stderr)
            return 1

        pending = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "panel.md", "content": "from panel"},
                session_id="panel-smoke",
            )
        )
        if pending.status != ToolInvokeStatus.draft_pending:
            print(f"FAIL create draft {pending}", file=sys.stderr)
            return 1

        page = client.get("/")
        if "工具草稿确认" not in page.text:
            print("FAIL html page", file=sys.stderr)
            return 1

        rows = client.get("/api/drafts").json()
        if not rows or rows[0]["draft_id"] != pending.draft_id:
            print(f"FAIL list drafts {rows}", file=sys.stderr)
            return 1

        approved = client.post(f"/api/drafts/{pending.draft_id}/approve")
        if approved.status_code != 200:
            print(f"FAIL approve {approved.status_code} {approved.text}", file=sys.stderr)
            return 1
        body = approved.json()
        if body.get("status") != "executed":
            print(f"FAIL approve body {body}", file=sys.stderr)
            return 1

        out = sandbox / "panel.md"
        if not out.is_file() or "from panel" not in out.read_text(encoding="utf-8"):
            print("FAIL file not written after panel approve", file=sys.stderr)
            return 1

        after = client.get("/api/drafts").json()
        if after:
            print(f"FAIL drafts still pending {after}", file=sys.stderr)
            return 1

        pending2 = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "reject.md", "content": "x"},
                session_id="panel-smoke-2",
            )
        )
        rej = client.post(
            f"/api/drafts/{pending2.draft_id}/reject",
            json={"reason": "test"},
        )
        if rej.status_code != 200 or rej.json().get("status") != "rejected":
            print(f"FAIL reject {rej.text}", file=sys.stderr)
            return 1

        svc.close()
        print("smoke_draft_panel: PASS")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
