#!/usr/bin/env python3
"""Smoke Hermes MCP tool handlers (M6 D2)."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(_REPO))

from agent_platform.integrations.hermes import tools_mcp as tm  # noqa: E402


def main() -> int:
    from agent_platform.tools.service import ToolService

    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "store"
        sandbox = Path(td) / "sandbox"
        sandbox.mkdir()
        (sandbox / "in.txt").write_text("hermes-m6", encoding="utf-8")
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
        }
        tm._get_tool_service = lambda: ToolService(  # type: ignore[method-assign]
            config=cfg, store_root=root, sandbox_root=sandbox
        )

        st = json.loads(tm.agent_tool_status({}, current_session_id="smoke-m6"))
        assert st.get("success") and st.get("enabled")
        assert any(t.get("tool") == "read_file" for t in st.get("tools", []))

        read = json.loads(
            tm.agent_tool_invoke(
                {
                    "server": "filesystem",
                    "tool": "read_file",
                    "arguments": {"path": "in.txt"},
                },
                current_session_id="smoke-m6",
            )
        )
        assert read.get("status") == "executed"
        assert read.get("output", {}).get("content") == "hermes-m6"

        pending = json.loads(
            tm.agent_tool_invoke(
                {
                    "server": "filesystem",
                    "tool": "write_file",
                    "arguments": {"path": "out.txt", "content": "from hermes"},
                },
                current_session_id="smoke-m6",
            )
        )
        assert pending.get("status") == "draft_pending"
        draft_id = pending.get("draft_id")
        assert draft_id

        listed = json.loads(
            tm.agent_tool_list_drafts({}, current_session_id="smoke-m6")
        )
        assert listed.get("count") >= 1

        done = json.loads(
            tm.agent_tool_approve_draft(
                {"draft_id": draft_id},
                current_session_id="smoke-m6",
            )
        )
        assert done.get("status") == "executed"
        assert (sandbox / "out.txt").read_text(encoding="utf-8") == "from hermes"

        rej = json.loads(
            tm.agent_tool_invoke(
                {
                    "server": "filesystem",
                    "tool": "write_file",
                    "arguments": {"path": "cancel.txt", "content": "x"},
                },
                current_session_id="smoke-m6b",
            )
        )
        rid = rej.get("draft_id")
        rj = json.loads(tm.agent_tool_reject_draft({"draft_id": rid}))
        assert rj.get("status") == "rejected"

    print("smoke_hermes_tools_mcp: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
