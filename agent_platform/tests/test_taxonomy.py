"""Phase 3 — Taxonomy tests."""

from __future__ import annotations

import pytest

from agent_platform.learning.taxonomy import TaxonomyService, gap_id_for_error_code


def test_gap_id_format() -> None:
    assert gap_id_for_error_code("CARRY_ERROR") == "gap-carry-error"


def test_lookup_known_code() -> None:
    tax = TaxonomyService()
    entry = tax.lookup("CARRY_ERROR")
    assert entry.title == "进位错误"
    assert entry.gap_id == "gap-carry-error"


def test_lookup_unknown_raises() -> None:
    tax = TaxonomyService()
    with pytest.raises(KeyError):
        tax.lookup("NOT_A_REAL_CODE")
