"""Parse English sample .kp.md."""

from __future__ import annotations

from pathlib import Path

from agent_platform.learning.kp_document_parser import parse_kp_document

REPO_ROOT = Path(__file__).resolve().parents[2]
ENGLISH_SAMPLE = REPO_ROOT / "docs" / "content" / "英语-三年级.kp.md"


def test_english_sample_kp_md_parses() -> None:
    draft = parse_kp_document(ENGLISH_SAMPLE)
    assert draft.subject == "英语"
    assert draft.grade == 3
    assert len(draft.units) >= 2
    assert draft.has_questions()
    assert draft.has_knowledge_points()
    starter = next(u for u in draft.units if u.unit_id == "english-g3-starter")
    assert len(starter.knowledge_points) >= 4
    assert any(q.default_error_code == "SPELLING_ERROR" for u in draft.units for q in u.questions)
