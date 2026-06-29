"""M6 D4 — draft panel API."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[2]
_SMOKE = _REPO / "agent_platform" / "tools" / "smoke_draft_panel.py"


def test_smoke_draft_panel_subprocess():
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
    assert "smoke_draft_panel: PASS" in r.stdout
