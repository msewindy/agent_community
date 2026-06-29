#!/usr/bin/env python3
"""Phase 1 acceptance — StudentContext init, persist, prompt block."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.contracts import PipelineStage, StudentContextPatch
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase1() -> int:
    with tempfile.TemporaryDirectory(prefix="learning-p1-") as td:
        root = Path(td) / "student_data"
        svc = StudentContextService(data_root=root)
        sid = "demo-stu-01"

        ctx = svc.init_from_defaults(sid)
        if ctx.curriculum.unit_title != "100以内加减法":
            return _fail(f"init defaults unit_title: {ctx.curriculum.unit_title}")

        path = root / sid / "context.json"
        if not path.is_file():
            return _fail("context.json missing")

        svc2 = StudentContextService(data_root=root)
        ctx2 = svc2.get(sid)
        if ctx2.student_id != sid:
            return _fail("cross-read student_id")

        block = svc2.to_prompt_block(ctx2)
        if "100以内加减法" not in block or "StudentContext" not in block:
            return _fail(f"prompt block: {block[:200]}")

        before = ctx2.updated_at
        ctx3 = svc2.patch(sid, StudentContextPatch(pipeline_stage=PipelineStage.practice))
        if ctx3.pipeline_stage != PipelineStage.practice:
            return _fail("patch stage")
        if ctx3.updated_at <= before:
            return _fail("updated_at not refreshed")

        try:
            svc.init_from_defaults(sid)
            return _fail("init should raise FileExistsError")
        except FileExistsError:
            pass

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}
        r = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "show",
                sid,
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if r.returncode != 0:
            return _fail(f"cli show: {r.stderr}")

        pr = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "prompt",
                sid,
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if pr.returncode != 0 or "100以内加减法" not in pr.stdout:
            return _fail(f"cli prompt: {pr.stderr or pr.stdout}")

        raw = json.loads(path.read_text(encoding="utf-8"))
        if raw.get("schema_version") != "1.0.0":
            return _fail("schema_version")

        _ok("init_from_defaults + persist")
        _ok("cross-process StudentContextService read")
        _ok("to_prompt_block contains unit")
        _ok("patch refreshes updated_at")
        _ok("duplicate init rejected")
        _ok("context.json schema_version")

    print("accept_learning_phase1: PASS")
    return 0


def main() -> int:
    return accept_phase1()


if __name__ == "__main__":
    raise SystemExit(main())
