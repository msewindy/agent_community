#!/usr/bin/env python3
"""Full Student Jarvis acceptance — phases 1 through 7."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def _run(script: Path) -> int:
    repo = Path(__file__).resolve().parents[2]
    env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}
    r = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(repo),
        env=env,
        check=False,
    )
    return r.returncode


def main() -> int:
    base = Path(__file__).resolve().parent
    scripts = [
        base / "accept_learning_phase1.py",
        base / "accept_learning_phase2.py",
        base / "accept_learning_phase3.py",
        base / "accept_learning_phase4.py",
        base / "accept_learning_phase5.py",
        base / "accept_learning_phase6.py",
        base / "accept_learning_phase7.py",
        base / "accept_learning_p0_smoke.py",
    ]
    for script in scripts:
        print(f"=== {script.name} ===")
        code = _run(script)
        if code != 0:
            print(f"accept_learning_full: FAIL at {script.name}", file=sys.stderr)
            return code
    print("accept_learning_full: PASS (phases 1-7 + P0 smoke)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
