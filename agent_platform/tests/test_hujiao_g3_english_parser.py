"""Tests for 沪教三年级英语 PDF parser."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.hujiao_g3_english_ingest import DEFAULT_SUMMARY, DEFAULT_TEXTBOOK
from agent_platform.learning.hujiao_g3_english_parser import (
    build_kp_document,
    parse_summary_pdf,
)


@pytest.mark.skipif(not DEFAULT_SUMMARY.is_file(), reason="summary PDF not in workspace")
def test_parse_summary_has_ten_units() -> None:
    units = parse_summary_pdf(DEFAULT_SUMMARY)
    assert len(units) == 10
    u1 = units[1]
    assert u1.unit_id == "english-g3-u01"
    assert any(v.english == "school" for v in u1.core_vocab)
    assert any("goal" in s.english.lower() for s in u1.sentences)


@pytest.mark.skipif(
    not DEFAULT_SUMMARY.is_file() or not DEFAULT_TEXTBOOK.is_file(),
    reason="PDFs not in workspace",
)
def test_build_draft_structure() -> None:
    draft, exercises = build_kp_document(DEFAULT_SUMMARY, DEFAULT_TEXTBOOK)
    assert draft.subject == "英语"
    assert draft.grade == 3
    assert len(draft.units) == 10
    assert draft.knowledge_point_count == 40
    assert draft.question_count >= 10
    assert len(exercises) >= 30
    assert all(u.unit_id.startswith("english-g3-u") for u in draft.units)
