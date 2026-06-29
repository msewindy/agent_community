"""P1-B — kp_catalog diff tests."""

from __future__ import annotations

from pathlib import Path

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_catalog_diff import ConflictKind, KpChangeKind, UnitChangeKind
from agent_platform.learning.kp_document_parser import parse_kp_document

REPO_ROOT = Path(__file__).resolve().parents[2]
MATH_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"


def test_list_tree_has_subject_grade_layers() -> None:
    tree = KpCatalogService().list_tree()
    assert tree.subjects
    math = next(s for s in tree.subjects if s.subject == "数学")
    g2 = next(g for g in math.grades if g.grade == 2)
    assert any(u.unit_id == "math-g2-add-sub-100" for u in g2.units)


def test_diff_math_sample_against_production_catalog() -> None:
    draft = parse_kp_document(MATH_SAMPLE)
    diff = KpCatalogService().diff_with_draft(draft)

    assert diff.summary.unit_count_draft == 2
    assert diff.summary.new_units >= 0

    existing = next(u for u in diff.units if u.unit_id == "math-g2-add-sub-100")
    assert existing.change in (UnitChangeKind.update_unit, UnitChangeKind.unchanged_unit)
    assert not any(c.kind == ConflictKind.unit_exists for c in diff.conflicts)

    multiply = next((u for u in diff.units if u.unit_id == "math-g2-multiply-table-2-5"), None)
    if multiply is not None:
        assert multiply.change in (UnitChangeKind.new_unit, UnitChangeKind.update_unit, UnitChangeKind.unchanged_unit)

    carry = next(
        kp for kp in existing.knowledge_points if kp.knowledge_point_id == "kp-g2-add-carry"
    )
    assert carry.change == KpChangeKind.unchanged

    align = next(
        kp for kp in existing.knowledge_points if kp.knowledge_point_id == "kp-g2-align-digits"
    )
    assert align.change in (KpChangeKind.new, KpChangeKind.unchanged)
