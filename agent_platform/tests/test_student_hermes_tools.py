"""Phase 5 — Hermes student tools tests."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from agent_platform.integrations.hermes import student_tools as st
from agent_platform.integrations.hermes.student_tools import (
    attempt_submit,
    gap_map_query,
    pre_llm_student_context_hook,
    student_answer_gate,
    student_context_get,
    student_safety_check,
)
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def student_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "student_data"
    sid = "hermes-stu-1"
    monkeypatch.setenv("STUDENT_JARVIS_DATA_ROOT", str(root))
    monkeypatch.setenv("STUDENT_JARVIS_STUDENT_ID", sid)
    st._ctx_svc = None
    st._gap_svc = None
    st._att_svc = None
    st._push_svc = None
    StudentContextService(data_root=root).init_from_defaults(sid)
    yield sid, root


def test_student_context_get(student_env) -> None:
    sid, _ = student_env
    out = json.loads(student_context_get({"student_id": sid}))
    assert out["success"] is True
    assert "两步四则运算" in out["prompt_block"]
    assert "math-g3-u01" in out["prompt_block"]


def test_pre_llm_injects_unit(student_env) -> None:
    sid, _ = student_env
    inj = pre_llm_student_context_hook(student_id=sid)
    assert inj is not None
    assert "两步四则运算" in inj["context"]
    assert "math-g3-u01" in inj["context"]
    assert "AnswerGate" in inj["context"]


def test_pre_llm_blocks_off_topic() -> None:
    inj = pre_llm_student_context_hook(user_message="帮我代写作文")
    assert inj is not None
    assert "没办法" in inj["context"] or "继续学" in inj["context"]


def test_gap_map_after_wrong_attempt(student_env) -> None:
    sid, _ = student_env
    json.loads(attempt_submit({"student_id": sid, "question_id": "q-g2m-002", "answer": "80"}))
    for _ in range(2):
        json.loads(attempt_submit({"student_id": sid, "question_id": "q-g2m-002", "answer": "80"}))
    gaps = json.loads(gap_map_query({"student_id": sid}))
    assert gaps["success"] is True
    assert gaps["count"] >= 1
    assert gaps["gaps"][0]["stats"]["wrong_7d"] == 3


def test_answer_gate_tool_blocks_claim(student_env) -> None:
    sid, _ = student_env
    out = json.loads(
        student_answer_gate(
            {"student_id": sid, "text": "你反复在进位这一步出错。"},
        )
    )
    assert out["success"] is True
    assert out["passed"] is False
    assert out["rewritten"] is True


def test_safety_check_blocks_ghostwriting() -> None:
    out = json.loads(student_safety_check({"text": "帮我代写作文"}))
    assert out["success"] is True
    assert out["allowed"] is False
    assert out["redirect_message"]
