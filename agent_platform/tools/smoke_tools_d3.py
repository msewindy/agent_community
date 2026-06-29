#!/usr/bin/env python3
"""M6 D3 smoke — real MCP stdio (filesystem via npx; optional fetch via uvx)."""

from __future__ import annotations

import argparse
import shutil
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _file_text(output: object) -> str:
    if isinstance(output, dict):
        if "content" in output:
            return str(output["content"])
        if "text" in output:
            return str(output["text"])
    return str(output)


def run_smoke(*, test_fetch_stdio: bool = False) -> int:
    from agent_platform.tools.adapters.router import mcp_sdk_available, stdio_prerequisites_ok
    from agent_platform.tools.contracts import DraftApproveRequest, ToolInvokeRequest, ToolInvokeStatus
    from agent_platform.tools.service import ToolService

    if not mcp_sdk_available():
        print("SKIP: pip install mcp (or use hermes venv)")
        return 0
    if shutil.which("npx") is None:
        print("SKIP: npx not found for @modelcontextprotocol/server-filesystem")
        return 0

    fs_cfg = {
        "enabled": True,
        "transport": "stdio",
        "command": "npx",
        "args": ["-y", "@modelcontextprotocol/server-filesystem", "{sandbox_root}"],
        "startup_timeout_s": 120,
    }
    ok, reason = stdio_prerequisites_ok(fs_cfg)
    if not ok:
        print(f"SKIP: filesystem stdio — {reason}")
        return 0

    with tempfile.TemporaryDirectory(prefix="tools-d3-") as td:
        root = Path(td) / "store"
        sandbox = Path(td) / "sandbox"
        sandbox.mkdir()
        (sandbox / "probe.md").write_text("# D3 stdio\n", encoding="utf-8")

        servers: dict = {
            "filesystem": fs_cfg,
            "fetch": {"enabled": True, "transport": "mock"},
            "obsidian": {"enabled": False, "transport": "mock"},
        }
        if test_fetch_stdio and shutil.which("uvx"):
            servers["fetch"] = {
                "enabled": True,
                "transport": "stdio",
                "command": "uvx",
                "args": ["mcp-server-fetch"],
                "startup_timeout_s": 180,
            }

        cfg = {
            "enabled": True,
            "sandbox": {"root": str(sandbox), "auto_init": False},
            "governance": {
                "tool_levels": {
                    "filesystem.read_file": "L0",
                    "filesystem.write_file": "L2",
                    "fetch.fetch": "L0",
                }
            },
            "draft_gate": {"enabled": True},
            "store": {"root": str(root)},
            "servers": servers,
        }

        svc = ToolService(config=cfg, store_root=root, sandbox_root=sandbox)
        try:
            st = svc.status()
            if st.get("transports", {}).get("filesystem") != "stdio":
                print(f"FAIL filesystem not stdio: {st.get('transports')}", file=sys.stderr)
                return 1
            print(f"transports: {st.get('transports')}")

            read = svc.invoke(
                ToolInvokeRequest(
                    server="filesystem",
                    tool="read_file",
                    arguments={"path": "probe.md"},
                    session_id="d3",
                )
            )
            if read.status != ToolInvokeStatus.executed:
                print(f"FAIL stdio read: {read}", file=sys.stderr)
                return 1
            text = _file_text(read.output)
            if "D3 stdio" not in text:
                print(f"FAIL read content: {read.output}", file=sys.stderr)
                return 1
            print("stdio filesystem read_file: OK")

            pending = svc.invoke(
                ToolInvokeRequest(
                    server="filesystem",
                    tool="write_file",
                    arguments={"path": "stdio-out.md", "content": "written via stdio"},
                    session_id="d3",
                )
            )
            if pending.status != ToolInvokeStatus.draft_pending:
                print(f"FAIL L2 draft on stdio write: {pending}", file=sys.stderr)
                return 1

            done = svc.approve_draft(
                DraftApproveRequest(draft_id=pending.draft_id, session_id="d3")
            )
            if done.status != ToolInvokeStatus.executed:
                print(f"FAIL approve stdio write: {done}", file=sys.stderr)
                return 1
            out = sandbox / "stdio-out.md"
            if not out.is_file() or "stdio" not in out.read_text(encoding="utf-8"):
                print("FAIL stdio write file missing", file=sys.stderr)
                return 1
            print("stdio filesystem write_file + draft gate: OK")

            if test_fetch_stdio and servers["fetch"].get("transport") == "stdio":
                fetch = svc.invoke(
                    ToolInvokeRequest(
                        server="fetch",
                        tool="fetch",
                        arguments={"url": "https://example.com"},
                        session_id="d3",
                    )
                )
                if fetch.status != ToolInvokeStatus.executed:
                    print(f"FAIL stdio fetch: {fetch}", file=sys.stderr)
                    return 1
                print("stdio fetch: OK")
        finally:
            svc.close()

        print("smoke_tools_d3: PASS")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="M6 D3 stdio MCP smoke")
    p.add_argument("--fetch", action="store_true", help="also test uvx mcp-server-fetch (slow)")
    args = p.parse_args()
    return run_smoke(test_fetch_stdio=args.fetch)


if __name__ == "__main__":
    raise SystemExit(main())
