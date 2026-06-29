#!/usr/bin/env python3
"""M6 D5 — unified smoke acceptance (D1–D4 + Hermes + panel + pytest)."""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_D1 = _REPO / "agent_platform" / "tools" / "smoke_tools_d1.py"
_D2 = _REPO / "agent_platform" / "tools" / "smoke_tools_d2.py"
_D3 = _REPO / "agent_platform" / "tools" / "smoke_tools_d3.py"
_D4 = _REPO / "agent_platform" / "tools" / "smoke_draft_panel.py"
_HERMES = _REPO / "agent_platform" / "integrations" / "hermes" / "smoke_hermes_tools_mcp.py"
_CLI = _REPO / "agent_platform" / "tools" / "cli_tools.py"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _run_py(script: Path, *args: str) -> int:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    return proc.returncode


def _npx_ok() -> bool:
    return shutil.which("npx") is not None and _mcp_ok()


def _mcp_ok() -> bool:
    try:
        import mcp  # noqa: F401

        return True
    except ImportError:
        return False


def run_d1() -> int:
    return _run_py(_D1)


def run_d2() -> int:
    return _run_py(_D2)


def run_d3(*, with_fetch: bool) -> int:
    args = ("--fetch",) if with_fetch else ()
    return _run_py(_D3, *args)


def run_d4() -> int:
    return _run_py(_D4)


def run_hermes() -> int:
    return _run_py(_HERMES)


def run_cli_e2e() -> int:
    with tempfile.TemporaryDirectory(prefix="m6_accept_cli_") as td:
        root = Path(td) / "tools"
        cfg = root.parent / "accept_cli.yaml"
        cfg.write_text(
            f"""
enabled: true
sandbox:
  root: {root / 'sandbox'}
  auto_init: true
governance:
  tool_levels:
    filesystem.read_file: L0
    filesystem.write_file: L2
draft_gate:
  enabled: true
store:
  root: {root}
servers:
  filesystem:
    enabled: true
    transport: mock
  fetch:
    enabled: true
    transport: mock
panel:
  force_mock_transports: true
""".strip(),
            encoding="utf-8",
        )
        env = {**os.environ, "PYTHONPATH": str(_REPO)}

        def run(*args: str) -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                [sys.executable, str(_CLI), *args],
                cwd=str(_REPO),
                env=env,
                capture_output=True,
                text=True,
                check=False,
            )

        common = ["--root", str(root), "--config", str(cfg)]

        r = run(*common, "init")
        if r.returncode != 0:
            return _fail(f"cli init: {r.stderr}")

        r = run(
            *common,
            "invoke",
            "filesystem",
            "read_file",
            "--arguments",
            '{"path": "README.md"}',
        )
        if r.returncode != 0 or '"status": "executed"' not in r.stdout:
            return _fail(f"cli invoke read: {r.stdout}{r.stderr}")

        r = run(
            *common,
            "invoke",
            "filesystem",
            "write_file",
            "--arguments",
            '{"path": "cli-out.md", "content": "cli"}',
        )
        if r.returncode != 0 or "draft_pending" not in r.stdout:
            return _fail(f"cli invoke write draft: {r.stdout}{r.stderr}")

    _ok("CLI init / invoke L0 + L2 draft")
    return 0


def run_pytest() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-k",
            "(test_tools_ or test_hermes_tools_mcp or test_draft_panel) and not test_tools_accept",
            "-q",
        ],
        cwd=str(_REPO / "agent_platform"),
        env={**os.environ, "PYTHONPATH": str(_REPO)},
        check=False,
    )
    if proc.returncode != 0:
        return _fail(f"pytest exit {proc.returncode}")
    _ok("pytest -k tools")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="M6 D5 unified acceptance")
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--skip-hermes", action="store_true")
    p.add_argument("--skip-stdio", action="store_true", help="skip D3 real MCP stdio")
    p.add_argument("--skip-cli", action="store_true")
    p.add_argument("--fetch", action="store_true", help="D3 also test uvx mcp-server-fetch")
    args = p.parse_args()

    print("=== M6 accept_m6_smoke ===\n")

    if run_d1() != 0:
        print("\naccept_m6_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D1 mock MCP + L0/L2 draft gate")

    if run_d2() != 0:
        print("\naccept_m6_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D2 smoke_tools_d2 (Hermes handler path)")

    has_stdio = _npx_ok() and not args.skip_stdio
    if has_stdio:
        if run_d3(with_fetch=args.fetch) != 0:
            print("\naccept_m6_smoke: FAIL", file=sys.stderr)
            return 1
        label = "D3 stdio filesystem"
        if args.fetch:
            label += " + fetch"
        _ok(label)
    else:
        _skip("D3 stdio (need npx + mcp package, or pass --skip-stdio)")

    if run_d4() != 0:
        print("\naccept_m6_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D4 draft panel API")

    if not args.skip_hermes:
        if run_hermes() != 0:
            print("\naccept_m6_smoke: FAIL", file=sys.stderr)
            return 1
        _ok("D2 Hermes agent_tool_* tools")
    else:
        _skip("hermes agent_tool tools")

    if not args.skip_cli:
        code = run_cli_e2e()
        if code != 0:
            print("\naccept_m6_smoke: FAIL", file=sys.stderr)
            return code
    else:
        _skip("CLI e2e")

    if not args.skip_pytest:
        code = run_pytest()
        if code != 0:
            print("\naccept_m6_smoke: FAIL", file=sys.stderr)
            return code
    else:
        _skip("pytest")

    print("\naccept_m6_smoke: PASS — M6 D1–D5 pipeline OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
