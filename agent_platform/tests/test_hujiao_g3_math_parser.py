"""Tests for hujiao G3 math parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning._config import repo_root
from agent_platform.learning.g3_textbook_common import eval_simple_math, pending_exercises
from agent_platform.learning.hujiao_g3_math_parser import MATH_UNITS, build_kp_document


def test_eval_simple_math() -> None:
    assert eval_simple_math("3+4*5") == 23.0
    assert eval_simple_math("(6+3)*4") == 36.0


def test_math_units_count() -> None:
    assert len(MATH_UNITS) == 8


@pytest.mark.skipif(
    not any("数学" in p.name for p in (repo_root() / "三年级课本").glob("*.pdf")),
    reason="math PDF not present",
)
def test_build_kp_document_from_pdf() -> None:
    draft, exercises = build_kp_document(
        next(p for p in (repo_root() / "三年级课本").glob("*.pdf") if "数学" in p.name)
    )
    assert draft.subject == "数学"
    assert len(draft.units) == 8
    assert draft.units[0].unit_id == "math-g3-u01"
    assert len(draft.units[0].knowledge_points) >= 8
    assert draft.question_count >= 1
    assert len(pending_exercises(exercises)) >= 1
