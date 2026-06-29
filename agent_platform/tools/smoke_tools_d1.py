#!/usr/bin/env python3
"""M6 D1 smoke — L0 read + L2 draft gate + fetch mock."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def run_smoke() -> int:
    from agent_platform.tools.contracts import (
        DraftApproveRequest,
        ToolInvokeRequest,
        ToolInvokeStatus,
    )
    from agent_platform.tools.service import ToolService

    with tempfile.TemporaryDirectory(prefix="tools-d1-") as td:
        root = Path(td) / "store"
        sandbox = Path(td) / "sandbox"
        (sandbox / "notes").mkdir(parents=True)
        (sandbox / "notes" / "hello.md").write_text("# Hello\n\nM6 sandbox.\n", encoding="utf-8")

        cfg = {
            "enabled": True,
            "sandbox": {"root": str(sandbox), "auto_init": False},
            "governance": {
                "default_level": "L1",
                "tool_levels": {
                    "filesystem.read_file": "L0",
                    "filesystem.write_file": "L2",
                    "fetch.fetch": "L0",
                },
            },
            "draft_gate": {"enabled": True},
            "store": {"root": str(root)},
        }
        svc = ToolService(config=cfg, store_root=root, sandbox_root=sandbox)

        read = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="read_file",
                arguments={"path": "notes/hello.md"},
                session_id="d1",
            )
        )
        if read.status != ToolInvokeStatus.executed or "Hello" not in str(read.output):
            print(f"FAIL L0 read: {read}", file=sys.stderr)
            return 1
        print("L0 read_file: OK")

        fetch = svc.invoke(
            ToolInvokeRequest(
                server="fetch",
                tool="fetch",
                arguments={"url": "https://example.com"},
                session_id="d1",
            )
        )
        if fetch.status != ToolInvokeStatus.executed:
            print(f"FAIL L0 fetch: {fetch}", file=sys.stderr)
            return 1
        print("L0 fetch: OK")

        pending = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "notes/out.md", "content": "draft test"},
                session_id="d1",
            )
        )
        if pending.status != ToolInvokeStatus.draft_pending or not pending.draft_id:
            print(f"FAIL L2 draft: {pending}", file=sys.stderr)
            return 1
        print(f"L2 draft_pending: OK id={pending.draft_id[:8]}…")

        out_path = sandbox / "notes" / "out.md"
        if out_path.is_file():
            print("FAIL file written before approval", file=sys.stderr)
            return 1

        done = svc.approve_draft(
            DraftApproveRequest(draft_id=pending.draft_id, session_id="d1")
        )
        if done.status != ToolInvokeStatus.executed or not out_path.is_file():
            print(f"FAIL approve execute: {done}", file=sys.stderr)
            return 1
        print("L2 approve → write_file: OK")

        print("smoke_tools_d1: PASS")
    return 0


def main() -> int:
    return run_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
