#!/usr/bin/env python3
"""M6 D2 smoke — Hermes tool path (delegates to smoke_hermes_tools_mcp)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_HERMES = _REPO / "agent_platform" / "integrations" / "hermes" / "smoke_hermes_tools_mcp.py"


def main() -> int:
    env = {**__import__("os").environ, "PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [sys.executable, str(_HERMES)],
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        print("smoke_tools_d2: FAIL", file=sys.stderr)
        return proc.returncode
    print("smoke_tools_d2: PASS (Hermes handlers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
