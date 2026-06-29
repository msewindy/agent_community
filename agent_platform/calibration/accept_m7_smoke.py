#!/usr/bin/env python3
"""M7 D5 — unified smoke (D1–D3 + Hermes + panel + pytest)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_D1 = _REPO / "agent_platform" / "calibration" / "smoke_calibration_d1.py"
_PANEL = _REPO / "agent_platform" / "behavior" / "smoke_settings_panel.py"
_HERMES = _REPO / "agent_platform" / "integrations" / "hermes" / "smoke_hermes_calibration_tools.py"


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


def run_d1() -> int:
    return _run_py(_D1)


def run_panel() -> int:
    return _run_py(_PANEL)


def run_hermes() -> int:
    if not _HERMES.is_file():
        _skip("Hermes smoke script missing")
        return 0
    return _run_py(_HERMES)


def run_pytest(*, fast: bool) -> int:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    args = [
        sys.executable,
        "-m",
        "pytest",
        "agent_platform/tests/test_calibration.py",
        "agent_platform/tests/test_behavior.py",
        "-q",
    ]
    if fast:
        args.extend(["-k", "not slow"])
    proc = subprocess.run(args, cwd=str(_REPO), env=env, check=False)
    return proc.returncode


def main() -> int:
    p = argparse.ArgumentParser(description="M7 unified smoke")
    p.add_argument("--skip-hermes", action="store_true")
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--fast", action="store_true", default=True)
    args = p.parse_args()

    if run_d1() != 0:
        return _fail("M7 D1 smoke")
    _ok("M7 D1 calibration + behavior")

    if run_panel() != 0:
        return _fail("M7 settings panel")
    _ok("M7 D3 settings panel")

    if not args.skip_hermes:
        rc = run_hermes()
        if rc != 0:
            return _fail("M7 Hermes tools")
        _ok("M7 D2 Hermes tools")
    else:
        _skip("Hermes tools")

    if not args.skip_pytest:
        if run_pytest(fast=args.fast) != 0:
            return _fail("M7 pytest")
        _ok("M7 pytest")
    else:
        _skip("pytest")

    print("accept_m7_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
