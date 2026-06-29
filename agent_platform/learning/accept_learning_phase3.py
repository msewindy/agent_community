#!/usr/bin/env python3
"""Phase 3 acceptance — Gap map, taxonomy, focus sync."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.contracts import GapStatus
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase3() -> int:
    with tempfile.TemporaryDirectory(prefix="learning-p3-") as td:
        root = Path(td) / "student_data"
        ctx_svc = StudentContextService(data_root=root)
        att_svc = AttemptService(data_root=root, context_svc=ctx_svc)
        gap_svc = GapMapService(data_root=root)
        sid = "demo-stu-p3"

        ctx_svc.init_from_defaults(sid)

        empty = gap_svc.query(sid)
        if empty:
            return _fail("fresh student should have empty gaps")

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}

        lr = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "gap",
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
            return _fail(f"cli gap list empty student: {lr.stderr}")
        listed = json.loads(lr.stdout)
        if listed != []:
            return _fail(f"cli gap list should be [] got {listed}")
        if "mastered" in lr.stdout.lower():
            return _fail("empty gap list must not mention mastered")

        for _ in range(3):
            att_svc.submit(sid, "q-g2m-002", "80")

        gap = gap_svc.get_gap(sid, "gap-kp-g2-add-carry")
        if gap.stats.wrong_7d != 3:
            return _fail(f"wrong_7d={gap.stats.wrong_7d}")

        ctx = ctx_svc.get(sid)
        if "gap-kp-g2-add-carry" not in ctx.focus.top_gap_ids:
            return _fail(f"top_gap_ids={ctx.focus.top_gap_ids}")

        gap_path = root / sid / "gap_map.json"
        if not gap_path.is_file():
            return _fail("gap_map.json missing")

        att_svc.submit(sid, "q-g2m-002", "85")
        att_svc.submit(sid, "q-g2m-003", "83")
        att_svc.submit(sid, "q-g2m-009", "75")

        gap2 = gap_svc.get_gap(sid, "gap-kp-g2-add-carry")
        if gap2.status != GapStatus.mastered:
            return _fail(f"expected mastered, got {gap2.status}")

        ctx2 = ctx_svc.get(sid)
        if "gap-kp-g2-add-carry" in ctx2.focus.top_gap_ids:
            return _fail("mastered gap should leave top_gap_ids")

        sr = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "gap",
                "show",
                sid,
                "gap-kp-g2-add-carry",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if sr.returncode != 0:
            return _fail(f"cli gap show: {sr.stderr}")
        shown = json.loads(sr.stdout)
        if shown.get("status") != "mastered":
            return _fail(f"cli show status: {shown.get('status')}")

        _ok("empty student → gap list []")
        _ok("3 wrong → wrong_7d=3 + top_gap_ids")
        _ok("gap_map.json persisted")
        _ok("3 correct → mastered")
        _ok("mastered removed from top_gap_ids")
        _ok("cli gap list/show")

    print("accept_learning_phase3: PASS")
    return 0


def main() -> int:
    return accept_phase3()


if __name__ == "__main__":
    raise SystemExit(main())
