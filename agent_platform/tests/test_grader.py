"""Phase 2 — Grader tests."""

from __future__ import annotations

import pytest

from agent_platform.learning.contracts import AnswerType, Question
from agent_platform.learning.grader import Grader


@pytest.fixture
def grader() -> Grader:
    return Grader(default_numeric_tolerance=0.001)


def _q(**kwargs) -> Question:
    base = dict(
        question_id="q-test",
        unit_id="u1",
        knowledge_point_id="kp1",
        stem="test",
        answer_type=AnswerType.exact,
        expected_answer="6",
        explanation="because",
        default_error_code="ERR",
    )
    base.update(kwargs)
    return Question.model_validate(base)


def test_exact_match_ignores_outer_whitespace(grader: Grader) -> None:
    result = grader.grade(_q(), "  6  ")
    assert result.correct is True
    assert result.error_code is None


def test_exact_mismatch(grader: Grader) -> None:
    result = grader.grade(_q(), "5")
    assert result.correct is False
    assert result.error_code == "ERR"


def test_numeric_within_tolerance(grader: Grader) -> None:
    q = _q(answer_type=AnswerType.numeric, expected_answer="8", numeric_tolerance=0.01)
    assert grader.grade(q, "8.005").correct is True


def test_numeric_outside_tolerance(grader: Grader) -> None:
    q = _q(answer_type=AnswerType.numeric, expected_answer="8", numeric_tolerance=0.01)
    assert grader.grade(q, "8.02").correct is False
