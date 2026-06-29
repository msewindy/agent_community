#!/usr/bin/env python3
"""M4 D5 — unified smoke acceptance (D1–D4 + CLI + optional Hermes + pytest)."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

_CLI = _REPO / "agent_platform" / "perception" / "cli_perception.py"
_HERMES_SMOKE = _REPO / "agent_platform" / "integrations" / "hermes" / "smoke_hermes_perception_tools.py"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def _skip(msg: str) -> None:
    print(f"SKIP {msg}")


def _opencv_ok() -> bool:
    try:
        from agent_platform.perception.frames import opencv_available

        return opencv_available()
    except Exception:
        return False


def _run_py(script: Path, *args: str) -> int:
    env = {**os.environ, "PYTHONPATH": str(_REPO)}
    proc = subprocess.run(
        [sys.executable, str(script), *args],
        cwd=str(_REPO),
        env=env,
        check=False,
    )
    return proc.returncode


def _run_cli(*args: str) -> int:
    return _run_py(_CLI, *args)


def run_d1() -> int:
    from agent_platform.perception.smoke_perception_d1 import run_smoke

    return run_smoke()


def run_d2() -> int:
    from agent_platform.perception.smoke_perception_d2 import run_smoke

    return run_smoke()


def run_d3() -> int:
    from agent_platform.perception.smoke_perception_d3 import run_smoke

    return run_smoke()


def run_d4() -> int:
    from agent_platform.perception.smoke_perception_d4 import run_smoke

    return run_smoke()


def run_cli_e2e(root: Path) -> int:
    if _run_cli("init", "--root", str(root)) != 0:
        return _fail("cli init")
    _ok("cli init")
    if _run_cli("validate", "--root", str(root)) != 0:
        return _fail("cli validate")
    _ok("cli validate")
    if _run_cli("policy", "--root", str(root), "--camera", "on") != 0:
        return _fail("cli policy")
    _ok("cli policy --camera on")
    if (
        _run_cli(
            "orchestrate",
            "看下桌上那本书叫什么名字？",
            "--root",
            str(root),
            "--session-id",
            "accept-m4",
        )
        != 0
    ):
        return _fail("cli orchestrate")
    _ok("cli orchestrate (vision + describe)")
    return 0


def run_hermes_tools() -> int:
    if _run_py(_HERMES_SMOKE) != 0:
        return _fail("hermes perception tools smoke")
    _ok("hermes agent_perception_* handlers")
    return 0


def run_pytest() -> int:
    proc = subprocess.run(
        [
            sys.executable,
            "-m",
            "pytest",
            "tests/",
            "-k",
            "perception",
            "-q",
        ],
        cwd=str(_REPO / "agent_platform"),
        env={**os.environ, "PYTHONPATH": str(_REPO)},
        check=False,
    )
    if proc.returncode != 0:
        return _fail(f"pytest exit {proc.returncode}")
    _ok("pytest -k perception")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="M4 D5 unified acceptance")
    p.add_argument("--skip-pytest", action="store_true")
    p.add_argument("--skip-hermes", action="store_true")
    p.add_argument("--skip-opencv", action="store_true", help="skip D2–D4 (need OpenCV)")
    args = p.parse_args()

    print("=== M4 accept_m4_smoke ===\n")

    if run_d1() != 0:
        print("\naccept_m4_smoke: FAIL", file=sys.stderr)
        return 1
    _ok("D1 config + mock capture + ObserveEvent")

    has_cv = _opencv_ok() and not args.skip_opencv
    if not has_cv:
        _skip("D2–D4 (install opencv-python-headless)")
    else:
        for label, fn in (
            ("D2", run_d2),
            ("D3", run_d3),
            ("D4", run_d4),
        ):
            if fn() != 0:
                print("\naccept_m4_smoke: FAIL", file=sys.stderr)
                return 1
            _ok(f"{label} pipeline")

        with tempfile.TemporaryDirectory(prefix="m4_accept_cli_") as td:
            code = run_cli_e2e(Path(td) / "perception")
            if code != 0:
                print("\naccept_m4_smoke: FAIL", file=sys.stderr)
                return code

    if not args.skip_hermes and has_cv:
        code = run_hermes_tools()
        if code != 0:
            print("\naccept_m4_smoke: FAIL", file=sys.stderr)
            return code
    elif args.skip_hermes:
        _skip("hermes perception tools")
    elif not has_cv:
        _skip("hermes perception tools (needs OpenCV)")

    if not args.skip_pytest:
        code = run_pytest()
        if code != 0:
            print("\naccept_m4_smoke: FAIL", file=sys.stderr)
            return code
    else:
        _skip("pytest")

    print("\naccept_m4_smoke: PASS — M4 D1–D5 pipeline OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
