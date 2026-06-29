"""M6 D2 — Hermes MCP tool handlers smoke."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SMOKE = _REPO / "agent_platform" / "integrations" / "hermes" / "smoke_hermes_tools_mcp.py"


def test_smoke_hermes_tools_mcp():
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    r = subprocess.run(
        [sys.executable, str(_SMOKE)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
        check=False,
    )
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "smoke_hermes_tools_mcp: PASS" in r.stdout
