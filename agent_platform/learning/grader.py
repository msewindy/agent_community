"""Objective grader for seed question bank (Phase 2)."""

from __future__ import annotations

from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import AnswerType, GradeResult, Question


class Grader:
    def __init__(self, default_numeric_tolerance: Optional[float] = None) -> None:
        cfg = load_student_learning_config()
        default = (cfg.get("grader") or {}).get("numeric_tolerance", 0.001)
        self._default_tol = float(default_numeric_tolerance if default_numeric_tolerance is not None else default)

    def grade(self, question: Question, answer_raw: str) -> GradeResult:
        normalized = answer_raw.strip()
        if question.answer_type == AnswerType.exact:
            correct = normalized == question.expected_answer.strip()
        else:
            correct = self._numeric_match(
                normalized,
                question.expected_answer,
                question.numeric_tolerance or self._default_tol,
            )

        return GradeResult(
            correct=correct,
            answer_normalized=normalized,
            expected_answer=question.expected_answer,
            explanation=question.explanation,
            error_code=None if correct else question.default_error_code,
        )

    @staticmethod
    def _numeric_match(student: str, expected: str, tolerance: float) -> bool:
        try:
            student_val = float(student)
            expected_val = float(expected.strip())
        except ValueError:
            return False
        return abs(student_val - expected_val) <= tolerance
