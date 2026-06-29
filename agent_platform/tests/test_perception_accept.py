"""M4 D5 — accept_m4_smoke and cli_perception e2e."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_ACCEPT = _REPO / "agent_platform" / "perception" / "accept_m4_smoke.py"
_US2 = _REPO / "agent_platform" / "perception" / "accept_m4_us2.py"
_CLI = _REPO / "agent_platform" / "perception" / "cli_perception.py"


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


@pytest.mark.skipif(
    not __import__("agent_platform.perception.frames", fromlist=["opencv_available"]).opencv_available(),
    reason="opencv not installed",
)
def test_accept_m4_smoke_no_pytest():
    r = _run_py(_ACCEPT, "--skip-pytest")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "accept_m4_smoke: PASS" in r.stdout


@pytest.mark.skipif(
    not __import__("agent_platform.perception.frames", fromlist=["opencv_available"]).opencv_available(),
    reason="opencv not installed",
)
def test_accept_m4_us2():
    r = _run_py(_US2, "--skip-d5", "--skip-hermes")
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "accept_m4_us2: PASS" in r.stdout


def test_cli_init_validate(tmp_path: Path):
    root = tmp_path / "p"
    r = _run_py(_CLI, "init", "--root", str(root))
    assert r.returncode == 0, r.stderr
    r = _run_py(_CLI, "validate", "--root", str(root))
    assert r.returncode == 0, r.stderr
    r = _run_py(_CLI, "policy", "--root", str(root), "--camera", "off")
    assert r.returncode == 0, r.stderr
    assert "camera=False" in r.stdout
