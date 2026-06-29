#!/usr/bin/env python3
"""Phase 2 acceptance — Attempt submit, grader, session_stats."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase2() -> int:
    with tempfile.TemporaryDirectory(prefix="learning-p2-") as td:
        root = Path(td) / "student_data"
        ctx_svc = StudentContextService(data_root=root)
        att_svc = AttemptService(data_root=root, context_svc=ctx_svc)
        sid = "demo-stu-p2"

        ctx_svc.init_from_defaults(sid)

        for qid, ans in [
            ("q-g2m-001", "68"),
            ("q-g2m-002", "85"),
            ("q-g2m-003", "83"),
        ]:
            r = att_svc.submit(sid, qid, ans)
            if not r.correct:
                return _fail(f"expected correct for {qid}")

        ctx = ctx_svc.get(sid)
        if ctx.session_stats is None or ctx.session_stats.correct_rate_7d != 1.0:
            return _fail(f"after 3 correct, rate={getattr(ctx.session_stats, 'correct_rate_7d', None)}")

        wrong = att_svc.submit(sid, "q-g2m-004", "0")
        if wrong.correct:
            return _fail("wrong answer should be incorrect")
        if wrong.error_code != "CALCULATION_ERROR":
            return _fail(f"error_code: {wrong.error_code}")

        ctx2 = ctx_svc.get(sid)
        if ctx2.session_stats is None:
            return _fail("session_stats missing")
        if ctx2.session_stats.attempts_today != 4:
            return _fail(f"attempts_today={ctx2.session_stats.attempts_today}")
        if ctx2.session_stats.correct_rate_7d != 0.75:
            return _fail(f"correct_rate_7d={ctx2.session_stats.correct_rate_7d}")

        attempts_dir = root / sid / "attempts"
        if len(list(attempts_dir.glob("att-*.json"))) != 4:
            return _fail("attempt files count")

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}

        r = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "attempt",
                "submit",
                sid,
                "q-g2m-005",
                "34",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if r.returncode != 0:
            return _fail(f"cli submit: {r.stderr}")
        out = json.loads(r.stdout)
        if out.get("correct") is not True:
            return _fail(f"cli submit output: {out}")

        lr = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "attempt",
                "list",
                sid,
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if lr.returncode != 0:
            return _fail(f"cli list: {lr.stderr}")
        listed = json.loads(lr.stdout)
        if len(listed) != 5:
            return _fail(f"cli list count={len(listed)}")

        _ok("3 correct then rate=1.0")
        _ok("wrong answer sets error_code")
        _ok("4 attempts → correct_rate_7d=0.75")
        _ok("attempt json files on disk")
        _ok("cli attempt submit returns correct=true")
        _ok("cli attempt list")

    print("accept_learning_phase2: PASS")
    return 0


def main() -> int:
    return accept_phase2()


if __name__ == "__main__":
    raise SystemExit(main())
