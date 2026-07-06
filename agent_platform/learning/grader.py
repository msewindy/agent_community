"""Objective grader for seed question bank (Phase 2)."""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import AnswerType, GradeResult, Question

# 英语等拉丁字母答案：忽略大小写、撇号缩写与常见标点（don't ≈ do not）
_LATIN_PUNCT_RE = re.compile(r"[\s'’`\".,!?;:\-]+")
_CONTRACTIONS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"n't\b"), " not"),
    (re.compile(r"'re\b"), " are"),
    (re.compile(r"'ve\b"), " have"),
    (re.compile(r"'ll\b"), " will"),
    (re.compile(r"'m\b"), " am"),
    (re.compile(r"'d\b"), " would"),
)


class Grader:
    def __init__(self, default_numeric_tolerance: Optional[float] = None) -> None:
        cfg = load_student_learning_config()
        default = (cfg.get("grader") or {}).get("numeric_tolerance", 0.001)
        self._default_tol = float(default_numeric_tolerance if default_numeric_tolerance is not None else default)

    def grade(self, question: Question, answer_raw: str) -> GradeResult:
        normalized = answer_raw.strip()
        if question.answer_type == AnswerType.exact:
            correct = self._exact_match(normalized, question.expected_answer.strip())
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
    def _exact_match(student: str, expected: str) -> bool:
        if student == expected:
            return True
        if student.casefold() == expected.casefold():
            return True
        if Grader._is_latin_answer(student) and Grader._is_latin_answer(expected):
            return Grader._normalize_latin(student) == Grader._normalize_latin(expected)
        return False

    @staticmethod
    def _is_latin_answer(text: str) -> bool:
        s = text.strip()
        if not s:
            return False
        latin = sum(1 for c in s if c.isascii() and (c.isalpha() or c in "'’`-"))
        return latin / len(s) >= 0.75

    @staticmethod
    def _normalize_latin(text: str) -> str:
        s = text.casefold().strip()
        for pat, repl in _CONTRACTIONS:
            s = pat.sub(repl, s)
        return _LATIN_PUNCT_RE.sub("", s)

    @staticmethod
    def _numeric_match(student: str, expected: str, tolerance: float) -> bool:
        try:
            student_val = float(student)
            expected_val = float(expected.strip())
        except ValueError:
            return False
        return abs(student_val - expected_val) <= tolerance
