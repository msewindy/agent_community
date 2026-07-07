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
FULL_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-三年级-完整样例.kp.md"


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


def test_unit_without_kp_or_questions_raises() -> None:
    text = """---
学科: 数学
年级: 2
教材版本: test
---

# 单元：空单元
unit_id: math-g2-empty

## 知识点

"""
    with pytest.raises(KpDocumentParseError, match="must have knowledge points and/or practice questions"):
        parse_kp_document_text(text)


def test_parse_questions_only_unit() -> None:
    text = """---
学科: 数学
年级: 3
教材版本: test
---

# 单元：两步四则运算
unit_id: math-g3-u01

## 练习题

- 计算：6 + 3 × 4 = ? → q-g3m-t-001
  知识点: kp-math-g3-u01-mult-add
  答案: 18
  解析: 先乘后加
  错因: PROCEDURE_ERROR
"""
    draft = parse_kp_document_text(text)
    assert draft.is_questions_only()
    assert draft.question_count == 1
    assert draft.units[0].questions[0].question_id == "q-g3m-t-001"


def test_parse_kp_and_questions_combined() -> None:
    text = """---
学科: 数学
年级: 3
教材版本: test
---

# 单元：示例
unit_id: math-g3-ex

## 知识点

- 示例 → kp-g3-ex-01

## 练习题

- 1+1=? → q-g3-ex-001
  知识点: kp-g3-ex-01
  答案: 2
  解析: 加法
  错因: PROCEDURE_ERROR
"""
    draft = parse_kp_document_text(text)
    assert draft.knowledge_point_count == 1
    assert draft.question_count == 1
    qs = draft.to_questions()
    assert qs[0].unit_id == "math-g3-ex"


def test_parse_family_alpha_full_sample() -> None:
    draft = parse_kp_document(FULL_SAMPLE)
    assert draft.subject == "数学"
    assert draft.grade == 3
    assert draft.units[0].unit_id == "math-g3-u01"
    assert draft.knowledge_point_count == 8
    assert draft.question_count == 4
    kp = next(k for k in draft.units[0].knowledge_points if k.knowledge_point_id == "kp-math-g3-u01-mult-add")
    assert kp.description and "先算乘法" in kp.description
    q = draft.units[0].questions[0]
    assert q.default_error_code == "PROCEDURE_ERROR"
