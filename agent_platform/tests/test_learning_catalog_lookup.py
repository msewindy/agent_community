"""Tests for learning_catalog_lookup."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.learning_catalog_lookup import lookup_units

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def catalog(tmp_path: Path) -> KpCatalogService:
    path = tmp_path / "kp_catalog.json"
    path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    return KpCatalogService(catalog_path=path)


def test_english_unit_num_one(catalog: KpCatalogService) -> None:
    result = lookup_units(grade_level=3, subject="英语", unit_num=1, catalog=catalog)
    assert result.success is True
    assert result.unit is not None
    assert result.unit.unit_id == "english-g3-u01"
    assert "new start" in result.unit.unit_title.lower() or "A new start" in result.unit.unit_title


def test_unknown_unit_id(catalog: KpCatalogService) -> None:
    result = lookup_units(grade_level=3, unit_id="fake-unit", catalog=catalog)
    assert result.success is False


def test_title_contains_ambiguous_or_single(catalog: KpCatalogService) -> None:
    result = lookup_units(
        grade_level=3,
        subject="英语",
        title_contains="new start",
        catalog=catalog,
    )
    assert result.success is True
    assert result.unit is not None
    assert result.unit.unit_id == "english-g3-u01"
