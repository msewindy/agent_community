"""Fast acceptance tests for M8 scripts."""

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


def test_accept_m8_integration_fast() -> None:
    script = str(_REPO / "agent_platform" / "integration" / "accept_m8_integration.py")
    proc = _run(script, "--skip-us2", "--skip-hermes", "--skip-stdio")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "accept_m8_integration: PASS" in proc.stdout


def test_accept_m8_smoke_fast() -> None:
    script = str(_REPO / "agent_platform" / "integration" / "accept_m8_smoke.py")
    proc = _run(script, "--skip-pytest")
    assert proc.returncode == 0, proc.stderr + proc.stdout
    assert "accept_m8_smoke: PASS" in proc.stdout
