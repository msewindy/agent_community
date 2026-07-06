"""Catalog tree view + diff against `.kp.md` draft (P1-B)."""

from __future__ import annotations

from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field

from agent_platform.learning.kp_catalog import KpCatalogService, UnitCatalogEntry
from agent_platform.learning.kp_document_parser import KpDocumentDraft


class UnitChangeKind(str, Enum):
    new_unit = "new_unit"
    update_unit = "update_unit"
    unchanged_unit = "unchanged_unit"


class KpChangeKind(str, Enum):
    new = "new"
    unchanged = "unchanged"
    title_changed = "title_changed"
    missing_in_draft = "missing_in_draft"


class ConflictKind(str, Enum):
    unit_exists = "unit_exists"
    kp_title_mismatch = "kp_title_mismatch"
    kp_missing_in_draft = "kp_missing_in_draft"
    kp_cross_unit = "kp_cross_unit"
    subject_grade_mismatch = "subject_grade_mismatch"


class KpTreeNode(BaseModel):
    knowledge_point_id: str
    title: str


class UnitTreeNode(BaseModel):
    unit_id: str
    unit_title: str
    textbook_ref: Optional[str] = None
    knowledge_points: list[KpTreeNode] = Field(default_factory=list)


class GradeTreeNode(BaseModel):
    grade: int
    units: list[UnitTreeNode] = Field(default_factory=list)


class SubjectTreeNode(BaseModel):
    subject: str
    grades: list[GradeTreeNode] = Field(default_factory=list)


class CatalogTree(BaseModel):
    subjects: list[SubjectTreeNode] = Field(default_factory=list)


class CatalogConflict(BaseModel):
    conflict_id: str
    kind: ConflictKind
    message: str
    unit_id: Optional[str] = None
    knowledge_point_id: Optional[str] = None
    catalog_title: Optional[str] = None
    draft_title: Optional[str] = None
    catalog_unit_id: Optional[str] = None


class KpDiffItem(BaseModel):
    knowledge_point_id: str
    change: KpChangeKind
    draft_title: Optional[str] = None
    catalog_title: Optional[str] = None


class UnitDiffItem(BaseModel):
    unit_id: str
    change: UnitChangeKind
    draft_title: str
    catalog_title: Optional[str] = None
    knowledge_points: list[KpDiffItem] = Field(default_factory=list)


class CatalogDiffSummary(BaseModel):
    unit_count_draft: int = 0
    new_units: int = 0
    updated_units: int = 0
    unchanged_units: int = 0
    new_knowledge_points: int = 0
    unchanged_knowledge_points: int = 0
    title_changed_knowledge_points: int = 0
    missing_in_draft_knowledge_points: int = 0
    blocking_conflicts: int = 0


class CatalogDiff(BaseModel):
    subject: str
    grade: int
    units: list[UnitDiffItem] = Field(default_factory=list)
    conflicts: list[CatalogConflict] = Field(default_factory=list)
    summary: CatalogDiffSummary = Field(default_factory=CatalogDiffSummary)


def _unit_to_tree_node(unit: UnitCatalogEntry) -> UnitTreeNode:
    return UnitTreeNode(
        unit_id=unit.unit_id,
        unit_title=unit.unit_title,
        textbook_ref=unit.textbook_ref,
        knowledge_points=[
            KpTreeNode(knowledge_point_id=kp.knowledge_point_id, title=kp.title)
            for kp in unit.knowledge_points
        ],
    )


def build_catalog_tree(units: list[UnitCatalogEntry]) -> CatalogTree:
    by_subject: dict[str, dict[int, list[UnitTreeNode]]] = {}
    for unit in units:
        by_subject.setdefault(unit.subject, {}).setdefault(unit.grade, []).append(
            _unit_to_tree_node(unit)
        )

    subjects: list[SubjectTreeNode] = []
    for subject in sorted(by_subject.keys()):
        grades: list[GradeTreeNode] = []
        for grade in sorted(by_subject[subject].keys()):
            grade_units = sorted(by_subject[subject][grade], key=lambda u: u.unit_id)
            grades.append(GradeTreeNode(grade=grade, units=grade_units))
        subjects.append(SubjectTreeNode(subject=subject, grades=grades))
    return CatalogTree(subjects=subjects)


def diff_draft_against_catalog(
    draft: KpDocumentDraft,
    catalog_svc: KpCatalogService,
) -> CatalogDiff:
    catalog = catalog_svc.catalog
    catalog_by_unit = {u.unit_id: u for u in catalog.units}
    kp_index: dict[str, tuple[str, str]] = {}
    for unit in catalog.units:
        for kp in unit.knowledge_points:
            kp_index[kp.knowledge_point_id] = (unit.unit_id, kp.title)

    conflicts: list[CatalogConflict] = []
    units_diff: list[UnitDiffItem] = []
    summary = CatalogDiffSummary(unit_count_draft=len(draft.units))

    catalog_same_scope = [
        u
        for u in catalog.units
        if u.subject == draft.subject and u.grade == draft.grade
    ]
    if not catalog_same_scope and catalog.units:
        conflicts.append(
            CatalogConflict(
                conflict_id="scope:subject-grade",
                kind=ConflictKind.subject_grade_mismatch,
                message=(
                    f"draft subject={draft.subject!r} grade={draft.grade} "
                    f"has no existing catalog slice (first publish for this scope)"
                ),
            )
        )

    for draft_unit in draft.units:
        catalog_unit = catalog_by_unit.get(draft_unit.unit_id)

        if not draft_unit.knowledge_points:
            if catalog_unit is None:
                conflicts.append(
                    CatalogConflict(
                        conflict_id=f"unit-missing:{draft_unit.unit_id}",
                        kind=ConflictKind.unit_exists,
                        message=(
                            f"unit {draft_unit.unit_id!r} not in catalog; "
                            "questions-only upload requires an existing unit"
                        ),
                        unit_id=draft_unit.unit_id,
                    )
                )
            else:
                summary.unchanged_units += 1
                units_diff.append(
                    UnitDiffItem(
                        unit_id=draft_unit.unit_id,
                        change=UnitChangeKind.unchanged_unit,
                        draft_title=draft_unit.unit_title,
                        catalog_title=catalog_unit.unit_title,
                        knowledge_points=[],
                    )
                )
            continue

        kp_diffs: list[KpDiffItem] = []

        if catalog_unit is None:
            summary.new_units += 1
            for kp in draft_unit.knowledge_points:
                other = kp_index.get(kp.knowledge_point_id)
                if other and other[0] != draft_unit.unit_id:
                    conflicts.append(
                        CatalogConflict(
                            conflict_id=f"kp-cross:{kp.knowledge_point_id}",
                            kind=ConflictKind.kp_cross_unit,
                            message=(
                                f"kp {kp.knowledge_point_id} exists in unit {other[0]!r}, "
                                f"draft assigns to {draft_unit.unit_id!r}"
                            ),
                            unit_id=draft_unit.unit_id,
                            knowledge_point_id=kp.knowledge_point_id,
                            draft_title=kp.title,
                            catalog_title=other[1],
                            catalog_unit_id=other[0],
                        )
                    )
                else:
                    summary.new_knowledge_points += 1
                kp_diffs.append(
                    KpDiffItem(
                        knowledge_point_id=kp.knowledge_point_id,
                        change=KpChangeKind.new,
                        draft_title=kp.title,
                    )
                )
            units_diff.append(
                UnitDiffItem(
                    unit_id=draft_unit.unit_id,
                    change=UnitChangeKind.new_unit,
                    draft_title=draft_unit.unit_title,
                    knowledge_points=kp_diffs,
                )
            )
            continue

        catalog_kps = {kp.knowledge_point_id: kp.title for kp in catalog_unit.knowledge_points}
        draft_kp_ids = {kp.knowledge_point_id for kp in draft_unit.knowledge_points}
        unit_has_changes = draft_unit.unit_title != catalog_unit.unit_title

        for kp in draft_unit.knowledge_points:
            cat_title = catalog_kps.get(kp.knowledge_point_id)
            if cat_title is None:
                other = kp_index.get(kp.knowledge_point_id)
                if other and other[0] != draft_unit.unit_id:
                    conflicts.append(
                        CatalogConflict(
                            conflict_id=f"kp-cross:{kp.knowledge_point_id}",
                            kind=ConflictKind.kp_cross_unit,
                            message=(
                                f"kp {kp.knowledge_point_id} exists in unit {other[0]!r}"
                            ),
                            unit_id=draft_unit.unit_id,
                            knowledge_point_id=kp.knowledge_point_id,
                            draft_title=kp.title,
                            catalog_title=other[1],
                            catalog_unit_id=other[0],
                        )
                    )
                    change = KpChangeKind.new
                else:
                    summary.new_knowledge_points += 1
                    change = KpChangeKind.new
                unit_has_changes = True
            elif cat_title == kp.title:
                summary.unchanged_knowledge_points += 1
                change = KpChangeKind.unchanged
            else:
                summary.title_changed_knowledge_points += 1
                unit_has_changes = True
                change = KpChangeKind.title_changed
                conflicts.append(
                    CatalogConflict(
                        conflict_id=f"kp-title:{kp.knowledge_point_id}",
                        kind=ConflictKind.kp_title_mismatch,
                        message=f"kp {kp.knowledge_point_id!r} title differs",
                        unit_id=draft_unit.unit_id,
                        knowledge_point_id=kp.knowledge_point_id,
                        catalog_title=cat_title,
                        draft_title=kp.title,
                    )
                )
            kp_diffs.append(
                KpDiffItem(
                    knowledge_point_id=kp.knowledge_point_id,
                    change=change,
                    draft_title=kp.title,
                    catalog_title=cat_title,
                )
            )

        for kp_id, cat_title in catalog_kps.items():
            if kp_id not in draft_kp_ids:
                summary.missing_in_draft_knowledge_points += 1
                unit_has_changes = True
                kp_diffs.append(
                    KpDiffItem(
                        knowledge_point_id=kp_id,
                        change=KpChangeKind.missing_in_draft,
                        catalog_title=cat_title,
                    )
                )
                conflicts.append(
                    CatalogConflict(
                        conflict_id=f"kp-missing:{draft_unit.unit_id}:{kp_id}",
                        kind=ConflictKind.kp_missing_in_draft,
                        message=(
                            f"catalog kp {kp_id!r} missing from draft "
                            f"(P1 forbids silent delete)"
                        ),
                        unit_id=draft_unit.unit_id,
                        knowledge_point_id=kp_id,
                        catalog_title=cat_title,
                    )
                )

        if unit_has_changes:
            summary.updated_units += 1
            unit_change = UnitChangeKind.update_unit
        else:
            summary.unchanged_units += 1
            unit_change = UnitChangeKind.unchanged_unit

        units_diff.append(
            UnitDiffItem(
                unit_id=draft_unit.unit_id,
                change=unit_change,
                draft_title=draft_unit.unit_title,
                catalog_title=catalog_unit.unit_title,
                knowledge_points=kp_diffs,
            )
        )

    summary.blocking_conflicts = len(conflicts)
    return CatalogDiff(
        subject=draft.subject,
        grade=draft.grade,
        units=units_diff,
        conflicts=conflicts,
        summary=summary,
    )
