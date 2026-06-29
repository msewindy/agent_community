#!/usr/bin/env python3
"""Write a pending L2 draft into tools_data/drafts for the :8766 panel."""

from __future__ import annotations

import argparse
import sys
from copy import deepcopy
from pathlib import Path

from agent_platform.tools._config import load_mcp_config
from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus
from agent_platform.tools.service import ToolService


def _cfg_with_mock(cfg: dict) -> dict:
    out = deepcopy(cfg)
    servers = {}
    for name, sc in (out.get("servers") or {}).items():
        merged = dict(sc or {})
        merged["transport"] = "mock"
        servers[name] = merged
    out["servers"] = servers
    panel = dict(out.get("panel") or {})
    panel["force_mock_transports"] = True
    out["panel"] = panel
    return out


def main() -> int:
    p = argparse.ArgumentParser(
        description="Create a pending L2 draft in tools_data/drafts (for draft panel :8766)"
    )
    p.add_argument("--path", default="panel_test.md", help="Sandbox-relative file path")
    p.add_argument("--content", default="hello from seed_panel_draft", help="File content")
    p.add_argument("--session-id", default="panel-verify", help="session_id shown in panel")
    p.add_argument(
        "--mock",
        action="store_true",
        help="Use mock MCP transports (recommended for local panel verify)",
    )
    args = p.parse_args()

    cfg = load_mcp_config()
    if args.mock:
        cfg = _cfg_with_mock(cfg)

    svc = ToolService(config=cfg)
    try:
        result = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": args.path, "content": args.content},
                session_id=args.session_id,
            )
        )
    finally:
        svc.close()

    if result.status != ToolInvokeStatus.draft_pending or not result.draft_id:
        print(f"FAIL: expected draft_pending, got {result.status.value}", file=sys.stderr)
        print(result.model_dump_json(indent=2), file=sys.stderr)
        return 1

    panel = cfg.get("panel") or {}
    host = panel.get("host", "127.0.0.1")
    port = int(panel.get("port", 8766))
    drafts_dir = svc.store_root / (cfg.get("store") or {}).get("drafts_dir", "drafts")

    print("seed_panel_draft: OK")
    print(f"  draft_id   {result.draft_id}")
    print(f"  drafts_dir {drafts_dir}")
    print(f"  panel      http://{host}:{port}/")
    print(f"  api        http://{host}:{port}/api/drafts")
    print("Open the panel and click 刷新 (or wait for auto-refresh).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
