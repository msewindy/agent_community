#!/usr/bin/env python3
"""M5 D5 — unified smoke acceptance (D1–D4 + Hermes + voice bridge + pytest)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_D1 = _REPO / "agent_platform" / "proactive" / "smoke_proactive_d1.py"
_D2 = _REPO / "agent_platform" / "proactive" / "smoke_proactive_d2.py"
_HERMES = _REPO / "agent_platform" / "integrations" / "hermes" / "smoke_hermes_proactive_tools.py"
_VOICE = _REPO / "agent_platform" / "voice" / "smoke_voice_proactive.py"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _run_py(script: Path) -> int:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [sys.executable, str(script)],
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    return proc.returncode


def run_d1() -> int:
    return _run_py(_D1)


def run_d2() -> int:
    return _run_py(_D2)


def run_voice() -> int:
    from agent_platform.voice.smoke_voice_proactive import run_smoke

    return run_smoke()


def run_hermes() -> int:
    return _run_py(_HERMES)


def run_pytest() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-k",
            "proactive or voice_proactive",
            "-q",
        ],
        cwd=str(_REPO / "agent_platform"),
        env={**os.environ, "PYTHONPATH": str(_REPO)},
        check=False,
    )
    if proc.returncode != 0:
        return _fail(f"pytest exit {proc.returncode}")
    _ok("pytest -k proactive")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="M5 D5 unified acceptance")
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--skip-hermes", action="store_true")
    args = p.parse_args()

    print("=== M5 accept_m5_smoke ===\n")

    if run_d1() != 0:
        print("\naccept_m5_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D1 quiet_hours + work_break + dismiss snooze")

    if run_d2() != 0:
        print("\naccept_m5_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D2 memory dedup")

    if run_voice() != 0:
        print("\naccept_m5_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D4 VoiceProactiveBridge")

    if not args.skip_hermes:
        if run_hermes() != 0:
            print("\naccept_m5_smoke: FAIL", file=sys.stderr)
            return 1
        _ok("D2 Hermes agent_proactive_* tools")
    else:
        _skip("hermes proactive tools")

    if not args.skip_pytest:
        code = run_pytest()
        if code != 0:
            print("\naccept_m5_smoke: FAIL", file=sys.stderr)
            return code
    else:
        _skip("pytest")

    print("\naccept_m5_smoke: PASS — M5 D1–D5 pipeline OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
