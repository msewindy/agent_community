"""P1-1 — question bank ingest from .kp.md drafts."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_document_parser import parse_kp_document_text
from agent_platform.learning.question_bank_ingest import (
    import_draft_questions,
    validate_draft_questions,
)
from agent_platform.learning import sqlite_store


def _questions_text() -> str:
    return """---
学科: 数学
年级: 3
教材版本: test
---

# 单元：混合运算
unit_id: math-g3-mixed-ops

## 练习题

- 计算：6 + 3 × 4 = ? → q-ingest-001
  知识点: kp-g3-mix-mult-add
  答案: 18
  解析: 先乘后加
  错因: PROCEDURE_ERROR
"""


def test_validate_draft_questions_ok(tmp_path: Path) -> None:
    cat_path = tmp_path / "kp_catalog.json"
    cat_path.write_text(
        Path("agent_platform/learning/catalog/kp_catalog.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    catalog = KpCatalogService(catalog_path=cat_path)
    draft = parse_kp_document_text(_questions_text())
    result = validate_draft_questions(draft, catalog=catalog)
    assert result.ok is True
    assert result.question_count == 1


def test_validate_unknown_kp_fails(tmp_path: Path) -> None:
    cat_path = tmp_path / "kp_catalog.json"
    cat_path.write_text(
        Path("agent_platform/learning/catalog/kp_catalog.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    catalog = KpCatalogService(catalog_path=cat_path)
    draft = parse_kp_document_text(
        _questions_text().replace("kp-g3-mix-mult-add", "kp-does-not-exist")
    )
    result = validate_draft_questions(draft, catalog=catalog)
    assert result.ok is False
    assert any("not in catalog" in e for e in result.errors)


def test_import_draft_questions_merge(tmp_path: Path) -> None:
    cat_path = tmp_path / "kp_catalog.json"
    cat_path.write_text(
        Path("agent_platform/learning/catalog/kp_catalog.json").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    catalog = KpCatalogService(catalog_path=cat_path)
    db = tmp_path / "questions.db"
    from agent_platform.learning.question_bank import QuestionBankService

    bank = QuestionBankService(sqlite_path=db)
    draft = parse_kp_document_text(_questions_text())
    imported = import_draft_questions(draft, bank=bank, archive=False)
    assert imported.imported == 1
    assert sqlite_store.count_questions(db) == 1

    draft2 = parse_kp_document_text(
        _questions_text().replace("q-ingest-001", "q-ingest-002")
    )
    imported2 = import_draft_questions(draft2, bank=bank, archive=False)
    assert imported2.imported == 1
    assert sqlite_store.count_questions(db) == 2
