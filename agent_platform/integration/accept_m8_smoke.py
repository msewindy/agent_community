#!/usr/bin/env python3
"""M8 D1 — unified smoke: fast integration + pytest hook."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_INTEGRATION = _REPO / "agent_platform" / "integration" / "accept_m8_integration.py"


def _run_py(script: Path, *args: str) -> int:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    return proc.returncode


def run_integration(*, fast: bool) -> int:
    args = ["--skip-hermes", "--skip-stdio"]
    if fast:
        args.append("--skip-us2")  # OpenCV optional in CI
    return _run_py(_INTEGRATION, *args)


def run_pytest() -> int:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "agent_platform/tests/test_m8_accept.py",
            "agent_platform/integration/",
            "-q",
        ],
        cwd=str(_REPO),
        env=env,
        check=False,
    ).returncode


def main() -> int:
    p = argparse.ArgumentParser(description="M8 unified smoke")
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--full", action="store_true", help="include US-2 OpenCV acceptance")
    args = p.parse_args()

    if run_integration(fast=not args.full) != 0:
        print("FAIL M8 integration", file=sys.stderr)
        return 1
    print("OK   M8 integration regression")

    if not args.skip_pytest:
        if run_pytest() != 0:
            print("FAIL M8 pytest", file=sys.stderr)
            return 1
        print("OK   M8 pytest")
    else:
        print("SKIP pytest")

    print("accept_m8_smoke: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
