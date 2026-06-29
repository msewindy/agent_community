"""M6 D3 — stdio MCP (skipped without npx/mcp)."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SMOKE = _REPO / "agent_platform" / "tools" / "smoke_tools_d3.py"


@pytest.mark.skipif(shutil.which("npx") is None, reason="npx not installed")
def test_smoke_tools_d3_stdio():
    try:
        import mcp  # noqa: F401
    except ImportError:
        pytest.skip("mcp package not installed")

    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    r = subprocess.run(
        [sys.executable, str(_SMOKE)],
        capture_output=True,
        text=True,
        env=env,
        cwd=str(_REPO),
        timeout=180,
        check=False,
    )
    if r.returncode != 0 and "SKIP" in (r.stdout + r.stderr):
        pytest.skip(r.stdout + r.stderr)
    assert r.returncode == 0, f"stdout={r.stdout}\nstderr={r.stderr}"
    assert "smoke_tools_d3: PASS" in r.stdout
