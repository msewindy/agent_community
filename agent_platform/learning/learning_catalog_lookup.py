"""Closed-set catalog lookup for Hermes tools (L1 — not NLU)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.kp_catalog import GradeBoundaryError, KpCatalogService, UnitCatalogEntry, get_kp_catalog_service
from agent_platform.learning.subject_pilot import pilot_unit_id


_SUBJECT_ALIASES: dict[str, str] = {
    "数学": "数学",
    "语文": "语文",
    "英语": "英语",
    "math": "数学",
    "chinese": "语文",
    "english": "英语",
}


@dataclass
class CatalogUnitBrief:
    unit_id: str
    unit_title: str
    subject: str
    grade: int
    textbook_ref: Optional[str] = None
    knowledge_points: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "unit_title": self.unit_title,
            "subject": self.subject,
            "grade": self.grade,
            "textbook_ref": self.textbook_ref,
            "knowledge_points": self.knowledge_points,
        }


@dataclass
class CatalogLookupResult:
    success: bool
    ambiguous: bool = False
    candidates: list[CatalogUnitBrief] = field(default_factory=list)
    unit: Optional[CatalogUnitBrief] = None
    error: Optional[str] = None

    def to_dict(self) -> dict:
        out: dict = {
            "success": self.success,
            "ambiguous": self.ambiguous,
            "candidates": [c.to_dict() for c in self.candidates],
        }
        if self.unit:
            out["unit"] = self.unit.to_dict()
        if self.error:
            out["error"] = self.error
        return out


def _normalize_subject(raw: Optional[str]) -> Optional[str]:
    if not raw:
        return None
    key = raw.strip().lower()
    for alias, canonical in _SUBJECT_ALIASES.items():
        if alias.lower() == key or canonical == raw.strip():
            return canonical
    if raw.strip() in _SUBJECT_ALIASES.values():
        return raw.strip()
    return None


def _brief(unit: UnitCatalogEntry) -> CatalogUnitBrief:
    return CatalogUnitBrief(
        unit_id=unit.unit_id,
        unit_title=unit.unit_title,
        subject=unit.subject,
        grade=unit.grade,
        textbook_ref=unit.textbook_ref,
        knowledge_points=[
            {"knowledge_point_id": kp.knowledge_point_id, "title": kp.title}
            for kp in unit.knowledge_points
        ],
    )


def _english_unit_id(unit_num: int) -> str:
    return f"english-g3-u{unit_num:02d}"


def _units_for_subject_grade(
    catalog: KpCatalogService,
    *,
    subject: str,
    grade_level: int,
) -> list[UnitCatalogEntry]:
    units = catalog.list_units(grade_level=grade_level, subject=subject, exact_grade=True)
    return sorted(units, key=lambda u: u.unit_id)


def lookup_units(
    *,
    grade_level: int,
    subject: Optional[str] = None,
    unit_num: Optional[int] = None,
    unit_id: Optional[str] = None,
    title_contains: Optional[str] = None,
    catalog: Optional[KpCatalogService] = None,
) -> CatalogLookupResult:
    catalog = catalog or get_kp_catalog_service()
    subject_norm = _normalize_subject(subject)

    if unit_id:
        try:
            unit = catalog.get_unit(unit_id.strip())
        except KeyError:
            return CatalogLookupResult(success=False, error=f"unknown unit_id: {unit_id}")
        try:
            catalog.assert_student_may_access_unit(grade_level, unit.unit_id)
        except GradeBoundaryError as exc:
            return CatalogLookupResult(success=False, error=str(exc))
        return CatalogLookupResult(success=True, unit=_brief(unit))

    candidates: list[UnitCatalogEntry] = []

    if subject_norm and unit_num is not None:
        if subject_norm == "英语":
            uid = _english_unit_id(int(unit_num))
            try:
                catalog.assert_student_may_access_unit(grade_level, uid)
                candidates = [catalog.get_unit(uid)]
            except (KeyError, Exception):
                return CatalogLookupResult(
                    success=False,
                    error=f"no english unit for unit_num={unit_num}",
                )
        else:
            pool = _units_for_subject_grade(catalog, subject=subject_norm, grade_level=grade_level)
            idx = int(unit_num) - 1
            if idx < 0 or idx >= len(pool):
                return CatalogLookupResult(
                    success=False,
                    error=f"unit_num={unit_num} out of range for {subject_norm} grade {grade_level}",
                )
            candidates = [pool[idx]]

    elif subject_norm and title_contains:
        needle = title_contains.strip().lower()
        pool = _units_for_subject_grade(catalog, subject=subject_norm, grade_level=grade_level)
        candidates = [u for u in pool if needle in u.unit_title.lower() or needle in u.unit_id.lower()]

    elif title_contains:
        needle = title_contains.strip().lower()
        pool = catalog.list_units(grade_level=grade_level)
        candidates = [u for u in pool if needle in u.unit_title.lower() or needle in u.unit_id.lower()]

    elif subject_norm:
        cfg = load_student_learning_config()
        pilot_units = (cfg.get("pilot") or {}).get("units") or {}
        uid = pilot_unit_id(pilot_units, subject_norm)
        if uid:
            try:
                catalog.assert_student_may_access_unit(grade_level, uid)
                candidates = [catalog.get_unit(uid)]
            except (KeyError, Exception):
                pass
        if not candidates:
            pool = _units_for_subject_grade(catalog, subject=subject_norm, grade_level=grade_level)
            if len(pool) == 1:
                candidates = pool

    else:
        return CatalogLookupResult(
            success=False,
            error="provide unit_id, or subject+unit_num, or subject+title_contains, or subject alone",
        )

    if not candidates:
        return CatalogLookupResult(success=False, error="no matching unit in catalog")

    briefs = [_brief(u) for u in candidates]
    if len(briefs) > 1:
        return CatalogLookupResult(success=True, ambiguous=True, candidates=briefs)
    return CatalogLookupResult(success=True, unit=briefs[0])
