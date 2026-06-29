"""Knowledge point catalog + grade boundary (P0)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from agent_platform.learning._config import load_student_learning_config, repo_root


class KnowledgePointDef(BaseModel):
    knowledge_point_id: str
    title: str


class UnitCatalogEntry(BaseModel):
    unit_id: str
    grade: int = Field(ge=1, le=6)
    subject: str
    unit_title: str
    textbook_ref: Optional[str] = None
    knowledge_points: list[KnowledgePointDef] = Field(default_factory=list)


class KpCatalog(BaseModel):
    schema_version: str
    school_stage: str = "primary"
    units: list[UnitCatalogEntry] = Field(default_factory=list)


class GradeBoundaryError(ValueError):
    pass


class KpCatalogService:
    def __init__(self, catalog_path: Optional[Path] = None, config: Optional[dict] = None) -> None:
        cfg = config or load_student_learning_config()
        cat_cfg = cfg.get("kp_catalog") or {}
        if catalog_path is None:
            catalog_path = repo_root() / cat_cfg.get(
                "path",
                "agent_platform/learning/catalog/kp_catalog.json",
            )
        self._path = Path(catalog_path).resolve()
        raw = json.loads(self._path.read_text(encoding="utf-8"))
        self._catalog = KpCatalog.model_validate(raw)
        self._by_unit = {u.unit_id: u for u in self._catalog.units}

    @property
    def catalog(self) -> KpCatalog:
        return self._catalog

    def get_unit(self, unit_id: str) -> UnitCatalogEntry:
        unit = self._by_unit.get(unit_id)
        if unit is None:
            raise KeyError(f"unknown unit_id in catalog: {unit_id}")
        return unit

    def list_units(
        self,
        grade_level: Optional[int] = None,
        subject: Optional[str] = None,
        *,
        exact_grade: bool = False,
    ) -> list[UnitCatalogEntry]:
        """List catalog units.

        ``grade_level``: when set, include units with ``unit.grade <= grade_level``
        (student may review lower-grade KPs). Pass ``exact_grade=True`` for ``==`` match.
        """
        items = self._catalog.units
        if grade_level is not None:
            if exact_grade:
                items = [u for u in items if u.grade == grade_level]
            else:
                items = [u for u in items if u.grade <= grade_level]
        if subject is not None:
            items = [u for u in items if u.subject == subject]
        return items

    def assert_student_may_access_unit(self, student_grade_level: int, unit_id: str) -> None:
        unit = self.get_unit(unit_id)
        if unit.grade > student_grade_level:
            raise GradeBoundaryError(
                f"grade boundary: student grade {student_grade_level} cannot access unit grade {unit.grade} ({unit_id})"
            )

    def resolve_grade_level(self, grade_label: str, explicit: Optional[int] = None) -> int:
        if explicit is not None:
            return explicit
        mapping = {
            "一": 1,
            "二": 2,
            "三": 3,
            "四": 4,
            "五": 5,
            "六": 6,
        }
        for key, val in mapping.items():
            if key in grade_label:
                return val
        pilot = (load_student_learning_config().get("pilot") or {}).get("grade_level")
        if pilot:
            return int(pilot)
        return 2

    def list_tree(self):
        from agent_platform.learning.kp_catalog_diff import build_catalog_tree

        return build_catalog_tree(self.catalog.units)

    def diff_with_draft(self, draft):
        from agent_platform.learning.kp_catalog_diff import diff_draft_against_catalog

        return diff_draft_against_catalog(draft, self)
