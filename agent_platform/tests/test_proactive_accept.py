"""M5 D6–D10 — accept_m5_smoke and accept_m5_us5 e2e."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SMOKE = _REPO / "agent_platform" / "proactive" / "accept_m5_smoke.py"
_US5 = _REPO / "agent_platform" / "proactive" / "accept_m5_us5.py"


def _run_py(script: Path, *args: str) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
        check=False,
    )


def test_accept_m5_smoke_no_pytest():
    r = _run_py(_SMOKE, "--skip-pytest", "--skip-hermes")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "accept_m5_smoke: PASS" in r.stdout


def test_accept_m5_us5():
    r = _run_py(_US5, "--skip-d5", "--skip-hermes", "--skip-cli")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "accept_m5_us5: PASS" in r.stdout
