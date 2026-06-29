#!/usr/bin/env python3
"""Phase 5 acceptance — Hermes student tools + pre_llm + AnswerGate."""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

from agent_platform.integrations.hermes import student_tools as st
from agent_platform.integrations.hermes.student_tools import (
    attempt_submit,
    gap_map_query,
    pre_llm_student_context_hook,
    register_student_hermes_tools,
    student_answer_gate,
    student_context_get,
)
from agent_platform.learning.answer_gate import StudentAnswerGate
from agent_platform.learning.student_context import StudentContextService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_phase5() -> int:
    with tempfile.TemporaryDirectory(prefix="learning-p5-") as td:
        root = Path(td) / "student_data"
        sid = "demo-stu-p5"
        os.environ["STUDENT_JARVIS_DATA_ROOT"] = str(root)
        os.environ["STUDENT_JARVIS_STUDENT_ID"] = sid
        st._ctx_svc = None
        st._gap_svc = None
        st._att_svc = None
        st._push_svc = None

        StudentContextService(data_root=root).init_from_defaults(sid)

        inj = pre_llm_student_context_hook(student_id=sid)
        if not inj or "100以内加减法" not in inj.get("context", ""):
            return _fail(f"pre_llm missing unit: {inj}")

        ctx_out = json.loads(student_context_get({"student_id": sid}))
        if not ctx_out.get("success"):
            return _fail(f"student_context_get: {ctx_out}")

        gate = StudentAnswerGate()
        blocked = gate.check("你反复在进位计算上出错。", gaps=[])
        if blocked.passed:
            return _fail("answer_gate should block without gaps")

        for _ in range(3):
            r = json.loads(
                attempt_submit({"student_id": sid, "question_id": "q-g2m-002", "answer": "80"})
            )
            if r.get("success") is not True:
                return _fail(f"attempt_submit: {r}")

        gaps = json.loads(gap_map_query({"student_id": sid}))
        if gaps.get("count", 0) < 1:
            return _fail(f"gap_map_query: {gaps}")

        tool_ok = json.loads(
            student_answer_gate(
                {
                    "student_id": sid,
                    "text": "gap-kp-g2-add-carry 显示 wrong_7d=3，需巩固进位错误。",
                }
            )
        )
        if not tool_ok.get("passed"):
            return _fail(f"gate with gap_id should pass: {tool_ok}")

        class _Ctx:
            _hooks: dict = {}

            def register_hook(self, name, fn):
                self._hooks[name] = fn

            def register_tool(self, **kwargs):
                pass

        ctx = _Ctx()
        register_student_hermes_tools(ctx)
        if "pre_llm_call" not in ctx._hooks:
            return _fail("pre_llm hook not registered")

        _ok("pre_llm injects StudentContext")
        _ok("student_context_get")
        _ok("answer_gate blocks ungrounded claims")
        _ok("attempt_submit + gap_map_query")
        _ok("student_answer_gate with gap_id")
        _ok("register_student_hermes_tools hooks")

    print("accept_learning_phase5: PASS")
    return 0


def main() -> int:
    return accept_phase5()


if __name__ == "__main__":
    raise SystemExit(main())
