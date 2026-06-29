#!/usr/bin/env python3
"""C7 Phase 2 acceptance — Hermes hooks + tools (no live Hermes required)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path


def main() -> int:
    root = Path(__file__).resolve().parents[2]
    env = {"PYTHONPATH": str(root), **dict(__import__("os").environ)}

    steps = [
        ("accept_c7_phase1", [sys.executable, str(root / "agent_platform/evolution/accept_c7_phase1.py")]),
        ("smoke_hermes_evolution_hooks", [sys.executable, str(root / "agent_platform/integrations/hermes/smoke_hermes_evolution_hooks.py")]),
    ]
    ok = True
    for name, cmd in steps:
        r = subprocess.run(cmd, cwd=str(root), env=env)
        if r.returncode != 0:
            print(f"FAIL {name}", file=sys.stderr)
            ok = False
        else:
            print(f"OK   {name}")

    print()
    if ok:
        print("accept_hermes_evolution_phase2: PASS")
        return 0
    print("accept_hermes_evolution_phase2: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
