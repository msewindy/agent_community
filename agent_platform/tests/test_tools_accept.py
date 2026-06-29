"""M6 D5 — accept_m6_smoke e2e."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SMOKE = _REPO / "agent_platform" / "tools" / "accept_m6_smoke.py"
_US = _REPO / "agent_platform" / "tools" / "accept_m6_us.py"


def _run_accept(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
        timeout=300,
        check=False,
    )


def test_accept_m6_smoke_fast():
    """Mock + panel + Hermes; skip stdio for CI speed."""
    r = _run_accept(_SMOKE, "--skip-stdio", "--skip-cli")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "accept_m6_smoke: PASS" in r.stdout


def test_accept_m6_us_fast():
    """C2/C3 US acceptance without stdio/D5 regression."""
    r = _run_accept(_US, "--skip-stdio", "--skip-d5")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "accept_m6_us: PASS" in r.stdout
