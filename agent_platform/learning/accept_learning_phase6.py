#!/usr/bin/env python3
"""Phase 6 acceptance — study plan + learning proactive."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.contracts import ContextFlags, LearningProactiveEventType, StudentContextPatch
from agent_platform.learning.learning_proactive import LearningProactiveService
from agent_platform.learning.remediation_skills import list_skill_ids
from agent_platform.learning.study_plan import StudyPlanService
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase6() -> int:
    if len(list_skill_ids()) != 4:
        return _fail(f"expected 4 remediation skills, got {list_skill_ids()}")

    with tempfile.TemporaryDirectory(prefix="learning-p6-") as td:
        root = Path(td) / "student_data"
        ctx_svc = StudentContextService(data_root=root)
        att_svc = AttemptService(data_root=root, context_svc=ctx_svc)
        plan_svc = StudyPlanService(data_root=root, ctx_svc=ctx_svc)
        pro_svc = LearningProactiveService(data_root=root, ctx_svc=ctx_svc)
        sid = "demo-stu-p6"

        ctx_svc.init_from_defaults(sid)

        r1 = att_svc.submit(sid, "q-g2m-001", "68")
        if not any(m.event_type == LearningProactiveEventType.attempt_summary for m in r1.proactive):
            return _fail("missing attempt_summary on submit")
        if not r1.proactive[0].delivered:
            return _fail("summary should be delivered when DND off")

        for _ in range(2):
            att_svc.submit(sid, "q-g2m-002", "80")
        r3 = att_svc.submit(sid, "q-g2m-002", "80")
        if not any(m.event_type == LearningProactiveEventType.gap_recurrence for m in r3.proactive):
            return _fail(f"expected gap_recurrence on 3rd wrong: {[m.event_type for m in r3.proactive]}")

        plan = plan_svc.generate(sid)
        ctx = ctx_svc.get(sid)
        if ctx.focus.active_plan_id != plan.plan_id:
            return _fail(f"active_plan_id={ctx.focus.active_plan_id}")

        ctx_svc.patch(sid, StudentContextPatch(flags=ContextFlags(do_not_disturb=True)))
        r_dnd = att_svc.submit(sid, "q-g2m-003", "83")
        if any(m.delivered for m in r_dnd.proactive):
            return _fail("DND should suppress delivery")

        log_path = root / sid / "learning_proactive.jsonl"
        if not log_path.is_file():
            return _fail("learning_proactive.jsonl missing")

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}

        pr = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "proactive",
                "list",
                sid,
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if pr.returncode != 0:
            return _fail(f"cli proactive list: {pr.stderr}")
        listed = json.loads(pr.stdout)
        if not listed:
            return _fail("proactive list empty")

        _ok("4 remediation skills")
        _ok("attempt_summary delivered")
        _ok("gap_recurrence on 3rd wrong")
        _ok("study_plan sets active_plan_id")
        _ok("DND suppresses delivery")
        _ok("learning_proactive.jsonl + cli list")

    print("accept_learning_phase6: PASS")
    return 0


def main() -> int:
    return accept_phase6()


if __name__ == "__main__":
    raise SystemExit(main())
