"""M3 D8 — accept_m3_us4 wrapper test."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
_ACCEPT = _REPO / "agent_platform" / "wiki" / "accept_m3_us4.py"


def test_accept_m3_us4_subprocess():
    proc = subprocess.run(
        [sys.executable, str(_ACCEPT)],
        capture_output=True,
        text=True,
        cwd=str(_REPO),
        env={**__import__("os").environ, "PYTHONPATH": str(_REPO)},
        check=False,
    )
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "accept_m3_us4: PASS" in proc.stdout
