"""Tests for PEP G3 chinese parser."""

from __future__ import annotations

import pytest

from agent_platform.learning._config import repo_root
from agent_platform.learning.g3_textbook_common import pending_exercises
from agent_platform.learning.pep_g3_chinese_parser import CHINESE_UNIT_THEMES, build_kp_document


def test_chinese_unit_themes() -> None:
    assert len(CHINESE_UNIT_THEMES) == 8


@pytest.mark.skipif(
    not any("语文" in p.name for p in (repo_root() / "三年级课本").glob("*.pdf")),
    reason="chinese PDF not present",
)
def test_build_kp_document_from_pdf() -> None:
    draft, exercises = build_kp_document(
        next(p for p in (repo_root() / "三年级课本").glob("*.pdf") if "语文" in p.name)
    )
    assert draft.subject == "语文"
    assert len(draft.units) == 8
    assert draft.units[0].unit_id == "chinese-g3-u01"
    assert len(draft.units[0].knowledge_points) == 6
    assert len(pending_exercises(exercises)) >= 5
