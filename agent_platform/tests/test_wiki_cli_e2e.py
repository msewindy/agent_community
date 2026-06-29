"""M3 D5 — CLI and unified smoke e2e tests."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest

from agent_platform.wiki.smoke_wiki import run_smoke

_REPO = Path(__file__).resolve().parents[2]
_CLI = _REPO / "agent_platform" / "wiki" / "cli_wiki.py"
_SMOKE = _REPO / "agent_platform" / "wiki" / "smoke_wiki.py"
_ACCEPT = _REPO / "agent_platform" / "wiki" / "accept_m3_smoke.py"


def _run_py(script: Path, *args: str, env: dict | None = None) -> subprocess.CompletedProcess[str]:
    e = {**os.environ, "PYTHONPATH": str(_REPO)}
    if env:
        e.update(env)
    return subprocess.run(
        [sys.executable, str(script), *args],
        capture_output=True,
        text=True,
        env=e,
        cwd=str(_REPO),
        check=False,
    )


def test_run_smoke_direct(tmp_path: Path):
    root = tmp_path / "wiki"
    assert run_smoke(root, trace_id="pytest-direct") == 0


def test_cli_validate_init_ingest_query(tmp_path: Path):
    root = tmp_path / "wiki"
    r = _run_py(_CLI, "init", "--root", str(root))
    assert r.returncode == 0, r.stderr
    r = _run_py(_CLI, "validate", "--root", str(root))
    assert r.returncode == 0, r.stderr

    raw = root / "raw" / "articles" / "cli-e2e.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text("# CLI E2E\n\nEnd-to-end via cli_wiki.\n", encoding="utf-8")

    r = _run_py(
        _CLI,
        "ingest",
        "raw/articles/cli-e2e.md",
        "--topic",
        "CLI E2E",
        "--root",
        str(root),
        "--trace-id",
        "cli-e2e",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "wiki ingest: OK" in r.stdout

    r = _run_py(
        _CLI,
        "query",
        "CLI E2E end-to-end",
        "--root",
        str(root),
        "--limit",
        "5",
    )
    assert r.returncode == 0, r.stderr + r.stdout
    assert "wiki query:" in r.stdout
    assert "hit" in r.stdout.lower()


def test_smoke_wiki_cli_isolated():
    r = _run_py(_SMOKE, "--isolated", "--trace-id", "cli-smoke-isolated")
    assert r.returncode == 0, r.stderr + r.stdout
    assert "smoke_wiki: PASS" in r.stdout


def test_accept_m3_smoke():
    r = _run_py(_ACCEPT)
    assert r.returncode == 0, r.stderr + r.stdout
    assert "accept_m3_smoke: PASS" in r.stdout
