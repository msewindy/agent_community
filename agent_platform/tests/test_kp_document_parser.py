"""P1-A — kp_document_parser tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.kp_document_parser import (
    KpDocumentParseError,
    parse_kp_document,
    parse_kp_document_text,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MATH_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"


def test_parse_math_sample_file() -> None:
    draft = parse_kp_document(MATH_SAMPLE)
    assert draft.subject == "数学"
    assert draft.grade == 2
    assert len(draft.units) == 2
    assert draft.units[0].unit_id == "math-g2-add-sub-100"
    assert len(draft.units[0].knowledge_points) == 8
    assert draft.units[1].unit_id == "math-g2-multiply-table-2-5"
    assert draft.units[0].knowledge_points[1].knowledge_point_id == "kp-g2-add-no-carry"
    assert draft.units[0].knowledge_points[1].description == "两位数加两位数，个位相加不满十"


def test_parse_chinese_sample_file() -> None:
    draft = parse_kp_document(CHINESE_SAMPLE)
    assert draft.subject == "语文"
    assert len(draft.units) == 2
    assert draft.units[0].unit_id == "chinese-g2-sentence-basic"
    assert any(kp.knowledge_point_id == "kp-g2-punct-period" for kp in draft.units[0].knowledge_points)


def test_to_catalog_units() -> None:
    draft = parse_kp_document(MATH_SAMPLE)
    units = draft.to_catalog_units()
    assert units[0].subject == "数学"
    assert units[0].grade == 2
    assert units[0].knowledge_points[0].title == "相同数位对齐"


def test_missing_frontmatter_raises() -> None:
    with pytest.raises(KpDocumentParseError, match="frontmatter"):
        parse_kp_document_text("# 单元：测试\n\nunit_id: u1\n\n## 知识点\n\n- a → kp-g2-a")


def test_duplicate_kp_id_raises() -> None:
    text = """---
学科: 数学
年级: 2
教材版本: test
---

# 单元：测试
unit_id: math-g2-test

## 知识点

- 甲 → kp-g2-dup
- 乙 → kp-g2-dup
"""
    with pytest.raises(KpDocumentParseError, match="duplicate knowledge_point_id"):
        parse_kp_document_text(text)


def test_unit_without_kp_raises() -> None:
    text = """---
学科: 数学
年级: 2
教材版本: test
---

# 单元：空单元
unit_id: math-g2-empty

## 知识点

"""
    with pytest.raises(KpDocumentParseError, match="no knowledge points"):
        parse_kp_document_text(text)
