#!/usr/bin/env python3
"""Phase 4 acceptance — push queue, fetch, gap-driven reorder."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.push_engine import PushEngineService, dominant_gap_id
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase4() -> int:
    with tempfile.TemporaryDirectory(prefix="learning-p4-") as td:
        root = Path(td) / "student_data"
        ctx_svc = StudentContextService(data_root=root)
        bank = QuestionBankService()
        push_svc = PushEngineService(data_root=root, bank=bank, context_svc=ctx_svc)
        att_svc = AttemptService(
            data_root=root,
            context_svc=ctx_svc,
            question_bank=bank,
            push_engine=push_svc,
        )
        sid = "demo-stu-p4"
        ctx_svc.init_from_defaults(sid)

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}

        for _ in range(3):
            att_svc.submit(sid, "q-g2m-002", "80")

        queue1 = push_svc.get_queue(sid)
        if dominant_gap_id(queue1) != "gap-kp-g2-add-carry":
            return _fail(f"after wrong, dominant={dominant_gap_id(queue1)}")

        fetch = push_svc.fetch(sid, count=3)
        if len(fetch.questions) < 1:
            return _fail("fetch empty")
        if not all(g == "gap-kp-g2-add-carry" for g in fetch.gap_ids if g):
            return _fail(f"fetch gap_ids={fetch.gap_ids}")

        q0 = fetch.question_ids[0]
        ans = bank.get(q0).expected_answer
        att_svc.submit(sid, q0, ans)

        att_svc.submit(sid, "q-g2m-002", "85")
        att_svc.submit(sid, "q-g2m-003", "83")
        att_svc.submit(sid, "q-g2m-009", "75")

        att_svc.submit(sid, "q-g2m-005", "30")
        queue2 = push_svc.get_queue(sid)
        dom2 = dominant_gap_id(queue2)
        if dom2 == "gap-kp-g2-add-carry":
            return _fail("mastered gap still dominates queue")
        if dom2 != "gap-kp-g2-sub-borrow":
            return _fail(f"expected borrow-error dominant, got {dom2}")

        pq = root / sid / "push_queue.json"
        if not pq.is_file():
            return _fail("push_queue.json missing")

        ctx = ctx_svc.get(sid)
        if not ctx.focus.queue_head_question_ids:
            return _fail("focus.queue_head_question_ids empty")

        fr = subprocess.run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "push",
                "peek",
                sid,
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if fr.returncode != 0:
            return _fail(f"cli push peek: {fr.stderr}")
        peeked = json.loads(fr.stdout)
        if not peeked:
            return _fail("cli peek empty")

        _ok("wrong x3 → queue dominated by carry gap")
        _ok("fetch returns gap-aligned batch")
        _ok("answer fetched question + master gap")
        _ok("new gap dominates after mastery")
        _ok("push_queue.json + focus.queue_head")
        _ok("cli push peek")

    print("accept_learning_phase4: PASS")
    return 0


def main() -> int:
    return accept_phase4()


if __name__ == "__main__":
    raise SystemExit(main())
