"""Fast acceptance tests for M7 scripts."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]


def _run(script: str, *args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, script, *args],
        cwd=str(_REPO),
        env={**__import__("os").environ, "PYTHONPATH": str(_REPO)},
        capture_output=True,
        text=True,
        check=False,
    )


def test_accept_m7_smoke_fast() -> None:
    script = str(_REPO / "agent_platform" / "calibration" / "accept_m7_smoke.py")
    proc = _run(script, "--skip-pytest")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "accept_m7_smoke: PASS" in proc.stdout


def test_accept_m7_us_fast() -> None:
    script = str(_REPO / "agent_platform" / "calibration" / "accept_m7_us.py")
    proc = _run(script, "--skip-d5")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "accept_m7_us: PASS" in proc.stdout


def test_accept_m7_manual_fast() -> None:
    script = str(_REPO / "agent_platform" / "calibration" / "accept_m7_manual.py")
    proc = _run(script)
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "accept_m7_manual: PASS" in proc.stdout
