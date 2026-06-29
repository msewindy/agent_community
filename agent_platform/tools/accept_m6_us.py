#!/usr/bin/env python3
"""M6 D6–D10 — C2/C3 formal acceptance (MCP tools + L0–L2 draft gate)."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> bool:
    print(f"FAIL {msg}", file=sys.stderr)
    return False


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _isolated_dirs() -> tuple[Path, Path]:
    td = tempfile.mkdtemp(prefix="m6_us_")
    root = Path(td) / "store"
    sandbox = Path(td) / "sandbox"
    sandbox.mkdir(parents=True)
    return root, sandbox


def _tools_cfg(root: Path, sandbox: Path) -> dict:
    return {
        "enabled": True,
        "sandbox": {"root": str(sandbox), "auto_init": False},
        "governance": {
            "default_level": "L1",
            "tool_levels": {
                "filesystem.read_file": "L0",
                "filesystem.list_directory": "L0",
                "filesystem.write_file": "L2",
                "filesystem.delete_file": "L2",
                "fetch.fetch": "L0",
                "obsidian.search": "L0",
            },
        },
        "draft_gate": {"enabled": True},
        "store": {"root": str(root)},
        "servers": {
            "filesystem": {"enabled": True, "transport": "mock"},
            "fetch": {"enabled": True, "transport": "mock"},
            "obsidian": {"enabled": True, "transport": "mock"},
        },
        "panel": {"force_mock_transports": True},
    }


def _svc(root: Path, sandbox: Path):
    from agent_platform.tools.service import ToolService

    return ToolService(config=_tools_cfg(root, sandbox), store_root=root, sandbox_root=sandbox)


def m6_a1_l0_read() -> bool:
    """C2：L0 只读工具直接执行。"""
    from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus

    root, sandbox = _isolated_dirs()
    (sandbox / "doc.txt").write_text("us6-read", encoding="utf-8")
    svc = _svc(root, sandbox)
    try:
        res = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="read_file",
                arguments={"path": "doc.txt"},
                session_id="m6-a1",
            )
        )
        if res.status != ToolInvokeStatus.executed:
            return _fail(f"M6 A1 L0 read: {res}")
        text = str(res.output)
        if "us6-read" not in text:
            return _fail(f"M6 A1 content: {res.output}")
        _ok("M6 A1 C2 L0 read_file → executed immediately")
        return True
    finally:
        svc.close()


def m6_a2_l0_fetch() -> bool:
    """C2：fetch 只读直跑。"""
    from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus

    root, sandbox = _isolated_dirs()
    svc = _svc(root, sandbox)
    try:
        res = svc.invoke(
            ToolInvokeRequest(
                server="fetch",
                tool="fetch",
                arguments={"url": "https://example.com"},
                session_id="m6-a2",
            )
        )
        if res.status != ToolInvokeStatus.executed:
            return _fail(f"M6 A2 fetch: {res}")
        _ok("M6 A2 C2 fetch → executed (mock)")
        return True
    finally:
        svc.close()


def m6_a3_sandbox_escape() -> bool:
    """C2：沙箱外路径拒绝。"""
    from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus

    root, sandbox = _isolated_dirs()
    svc = _svc(root, sandbox)
    try:
        res = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="read_file",
                arguments={"path": "../../../etc/passwd"},
                session_id="m6-a3",
            )
        )
        if res.status != ToolInvokeStatus.error:
            return _fail(f"M6 A3 expected error, got {res}")
        _ok("M6 A3 C2 sandbox — path outside root blocked")
        return True
    finally:
        svc.close()


def m6_a4_l2_draft_pending() -> bool:
    """C3：L2 写操作 → draft_pending，不执行。"""
    from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus

    root, sandbox = _isolated_dirs()
    svc = _svc(root, sandbox)
    try:
        res = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "out.md", "content": "secret"},
                session_id="m6-a4",
            )
        )
        if res.status != ToolInvokeStatus.draft_pending or not res.draft_id:
            return _fail(f"M6 A4 draft_pending: {res}")
        if (sandbox / "out.md").is_file():
            return _fail("M6 A4 file written before approval")
        _ok("M6 A4 C3 L2 write → draft_pending (no execute)")
        return True
    finally:
        svc.close()


def m6_a5_l2_approve_execute() -> bool:
    """C3：approve 后执行落盘。"""
    from agent_platform.tools.contracts import (
        DraftApproveRequest,
        ToolInvokeRequest,
        ToolInvokeStatus,
    )

    root, sandbox = _isolated_dirs()
    svc = _svc(root, sandbox)
    try:
        pending = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "approved.md", "content": "ok"},
                session_id="m6-a5",
            )
        )
        done = svc.approve_draft(
            DraftApproveRequest(draft_id=pending.draft_id, session_id="m6-a5")
        )
        if done.status != ToolInvokeStatus.executed:
            return _fail(f"M6 A5 approve execute: {done}")
        if not (sandbox / "approved.md").is_file():
            return _fail("M6 A5 file missing after approve")
        _ok("M6 A5 C3 approve → write executed")
        return True
    finally:
        svc.close()


def m6_a6_l2_reject_no_write() -> bool:
    """C3：reject 后不执行。"""
    from agent_platform.tools.contracts import DraftRejectRequest, ToolInvokeRequest

    root, sandbox = _isolated_dirs()
    svc = _svc(root, sandbox)
    try:
        pending = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "reject.md", "content": "x"},
                session_id="m6-a6",
            )
        )
        svc.reject_draft(DraftRejectRequest(draft_id=pending.draft_id, reason="us6"))
        if (sandbox / "reject.md").is_file():
            return _fail("M6 A6 file exists after reject")
        _ok("M6 A6 C3 reject → no side effect")
        return True
    finally:
        svc.close()


def m6_a7_draft_panel_api() -> bool:
    """C3：草稿面板 API approve。"""
    from fastapi.testclient import TestClient

    from agent_platform.api.draft_panel import create_app
    from agent_platform.tools.contracts import ToolInvokeRequest, ToolInvokeStatus

    root, sandbox = _isolated_dirs()
    cfg = _tools_cfg(root, sandbox)
    svc = _svc(root, sandbox)
    try:
        pending = svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "panel.md", "content": "via panel"},
                session_id="m6-a7",
            )
        )
        client = TestClient(create_app(config=cfg, service=svc))
        rows = client.get("/api/drafts").json()
        if not any(r["draft_id"] == pending.draft_id for r in rows):
            return _fail(f"M6 A7 list drafts: {rows}")

        resp = client.post(f"/api/drafts/{pending.draft_id}/approve")
        if resp.status_code != 200 or resp.json().get("status") != "executed":
            return _fail(f"M6 A7 panel approve: {resp.status_code} {resp.text}")

        if not (sandbox / "panel.md").read_text(encoding="utf-8").startswith("via"):
            return _fail("M6 A7 panel approve file content")
        _ok("M6 A7 C3 draft panel POST approve → executed")
        return True
    finally:
        svc.close()


def m6_a8_hermes_tools() -> bool:
    """C2/C3：Hermes agent_tool_* 工具链。"""
    try:
        from agent_platform.integrations.hermes import tools_mcp as tm
    except ImportError as e:
        _skip(f"M6 A8 hermes: {e}")
        return True

    root, sandbox = _isolated_dirs()
    (sandbox / "h.txt").write_text("hermes-us6", encoding="utf-8")
    cfg = _tools_cfg(root, sandbox)
    from agent_platform.tools.service import ToolService

    svc = ToolService(config=cfg, store_root=root, sandbox_root=sandbox)
    tm._get_tool_service = lambda: svc  # type: ignore[method-assign]

    try:
        read = json.loads(
            tm.agent_tool_invoke(
                {
                    "server": "filesystem",
                    "tool": "read_file",
                    "arguments": {"path": "h.txt"},
                },
                current_session_id="m6-a8",
            )
        )
        if read.get("status") != "executed":
            return _fail(f"M6 A8 hermes read: {read}")

        write = json.loads(
            tm.agent_tool_invoke(
                {
                    "server": "filesystem",
                    "tool": "write_file",
                    "arguments": {"path": "hw.md", "content": "h"},
                },
                current_session_id="m6-a8",
            )
        )
        if write.get("status") != "draft_pending" or not write.get("panel_url"):
            return _fail(f"M6 A8 hermes L2 draft: {write}")

        done = json.loads(
            tm.agent_tool_approve_draft(
                {"draft_id": write["draft_id"]},
                current_session_id="m6-a8",
            )
        )
        if done.get("status") != "executed":
            return _fail(f"M6 A8 hermes approve: {done}")

        _ok("M6 A8 Hermes agent_tool_invoke + approve_draft + panel_url")
        return True
    finally:
        svc.close()


def m6_a9_events_audit() -> bool:
    """C3：events.log.md 审计。"""
    from agent_platform.tools.contracts import ToolInvokeRequest

    root, sandbox = _isolated_dirs()
    svc = _svc(root, sandbox)
    try:
        svc.invoke(
            ToolInvokeRequest(
                server="filesystem",
                tool="write_file",
                arguments={"path": "a.md", "content": "a"},
                session_id="m6-a9",
            )
        )
        log_path = root / "events.log.md"
        if not log_path.is_file():
            return _fail("M6 A9 events.log.md missing")
        text = log_path.read_text(encoding="utf-8")
        if "draft_pending" not in text:
            return _fail(f"M6 A9 log missing draft_pending: {text[-300:]}")
        _ok("M6 A9 events.log.md audit trail")
        return True
    finally:
        svc.close()


def m6_a10_governance_levels() -> bool:
    """C3：L0/L2 分级映射。"""
    from agent_platform.tools.contracts import ToolLevel
    from agent_platform.tools.governance import resolve_tool_level

    m = {
        "filesystem.read_file": "L0",
        "filesystem.write_file": "L2",
    }
    if resolve_tool_level("filesystem", "read_file", {}, level_map=m) != ToolLevel.L0:
        return _fail("M6 A10 L0 mapping")
    if resolve_tool_level("filesystem", "write_file", {}, level_map=m) != ToolLevel.L2:
        return _fail("M6 A10 L2 mapping")
    _ok("M6 A10 governance L0/L2 level map")
    return True


def m6_a11_stdio_filesystem() -> bool:
    """C2：真 MCP stdio filesystem（可选）。"""
    if shutil.which("npx") is None:
        _skip("M6 A11 stdio (npx missing)")
        return True
    try:
        import mcp  # noqa: F401
    except ImportError:
        _skip("M6 A11 stdio (mcp package missing)")
        return True

    from agent_platform.tools.smoke_tools_d3 import run_smoke

    if run_smoke(test_fetch_stdio=False) != 0:
        return _fail("M6 A11 smoke_tools_d3")
    _ok("M6 A11 C2 stdio filesystem read/write + draft")
    return True


def run_d5_regression(*, skip_stdio: bool) -> bool:
    from agent_platform.tools.accept_m6_smoke import main as smoke_main

    old_argv = sys.argv
    try:
        extra = ["--skip-cli", "--skip-pytest"]
        if skip_stdio:
            extra.append("--skip-stdio")
        sys.argv = ["accept_m6_smoke", *extra]
        if smoke_main() != 0:
            return _fail("M6 D5 regression accept_m6_smoke")
    finally:
        sys.argv = old_argv
    _ok("M6 D5 regression accept_m6_smoke")
    return True


def print_manual_checklist() -> None:
    print(
        """
--- 手动验收清单（D7–D9，签字用）---

D7 Hermes（agent-tools 插件）:
  bash agent_platform/integrations/hermes/install_plugin.sh
  hermes plugins enable agent-tools
  hermes tools enable agent_tools

  agent_tool_invoke server=filesystem tool=read_file arguments={"path":"README.md"}
    → status=executed
  agent_tool_invoke server=filesystem tool=write_file arguments={"path":"x.md","content":"hi"}
    → status=draft_pending, panel_url=http://127.0.0.1:8766/
  用户确认后 agent_tool_approve_draft draft_id=...

D8 草稿面板（浏览器）:
  PYTHONPATH=. python -m agent_platform.api.draft_panel
  → http://127.0.0.1:8766/ 待确认列表 → 确认执行 / 拒绝

D9 生产 stdio（可选）:
  config/mcp.yaml filesystem.transport: stdio
  PYTHONPATH=. python agent_platform/tools/smoke_tools_d3.py

签字表：docs/M6-us-acceptance.md §5
"""
    )


def main() -> int:
    p = argparse.ArgumentParser(description="M6 C2/C3 acceptance (D6–D10)")
    p.add_argument("--skip-d5", action="store_true")
    p.add_argument("--skip-hermes", action="store_true")
    p.add_argument("--skip-stdio", action="store_true")
    args = p.parse_args()

    print("=== accept_m6_us (C2/C3) ===\n")

    ok = True
    steps = [
        m6_a1_l0_read,
        m6_a2_l0_fetch,
        m6_a3_sandbox_escape,
        m6_a4_l2_draft_pending,
        m6_a5_l2_approve_execute,
        m6_a6_l2_reject_no_write,
        m6_a7_draft_panel_api,
        m6_a9_events_audit,
    ]
    for fn in steps:
        if not fn():
            ok = False

    if not m6_a10_governance_levels():
        ok = False

    if not args.skip_hermes and not m6_a8_hermes_tools():
        ok = False
    elif args.skip_hermes:
        _skip("M6 A8 Hermes agent_tool tools")

    if not args.skip_stdio and not m6_a11_stdio_filesystem():
        ok = False
    elif args.skip_stdio:
        _skip("M6 A11 stdio filesystem")

    if not args.skip_d5 and not run_d5_regression(skip_stdio=args.skip_stdio):
        ok = False
    elif args.skip_d5:
        _skip("D5 regression accept_m6_smoke")

    print()
    if ok:
        print("accept_m6_us: PASS — C2/C3 automated acceptance OK")
        print_manual_checklist()
        return 0
    print("accept_m6_us: FAIL", file=sys.stderr)
    print_manual_checklist()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
