"""Apply approved `.kp.md` draft into kp_catalog.json (P1-E)."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from agent_platform.learning.contracts import utc_now
from agent_platform.learning.kp_catalog import (
    KnowledgePointDef,
    KpCatalog,
    KpCatalogService,
    UnitCatalogEntry,
)
from agent_platform.learning.kp_catalog_diff import CatalogDiff
from agent_platform.learning.kp_document_parser import KpDocumentDraft, KpDocumentUnit
from agent_platform.learning.kp_ingest_review import ConflictResolutionEntry, ResolutionAction


class CatalogMergeReport(BaseModel):
    job_id: str
    units_added: list[str] = Field(default_factory=list)
    units_updated: list[str] = Field(default_factory=list)
    units_skipped: list[str] = Field(default_factory=list)
    knowledge_points_added: int = 0
    knowledge_points_updated: int = 0
    knowledge_points_removed: int = 0
    knowledge_points_kept: int = 0


class CatalogApproveResult(BaseModel):
    job_id: str
    catalog_path: str
    backup_path: str
    audit_path: str
    merge_report: CatalogMergeReport


def _conflict_map(
    resolutions: list[ConflictResolutionEntry],
) -> dict[str, ConflictResolutionEntry]:
    return {r.conflict_id: r for r in resolutions}


def _effective_kp_id(
    kp_id: str,
    resolutions: dict[str, ConflictResolutionEntry],
) -> Optional[str]:
    cross_id = f"kp-cross:{kp_id}"
    entry = resolutions.get(cross_id)
    if entry is None:
        return kp_id
    if entry.action == ResolutionAction.skip:
        return None
    if entry.action == ResolutionAction.rename_draft:
        return entry.new_knowledge_point_id or kp_id
    return kp_id


def _merge_unit_knowledge_points(
    catalog_unit: UnitCatalogEntry,
    draft_unit: KpDocumentUnit,
    resolutions: dict[str, ConflictResolutionEntry],
) -> tuple[list[KnowledgePointDef], CatalogMergeReport]:
    stats = CatalogMergeReport(job_id="")
    merged: dict[str, KnowledgePointDef] = {
        kp.knowledge_point_id: kp.model_copy() for kp in catalog_unit.knowledge_points
    }
    draft_kp_ids: set[str] = set()

    for draft_kp in draft_unit.knowledge_points:
        effective_id = _effective_kp_id(draft_kp.knowledge_point_id, resolutions)
        if effective_id is None:
            continue
        draft_kp_ids.add(effective_id)

        title = draft_kp.title
        if draft_kp.knowledge_point_id in merged:
            title_res = resolutions.get(f"kp-title:{draft_kp.knowledge_point_id}")
            if title_res and title_res.action == ResolutionAction.use_catalog:
                title = merged[draft_kp.knowledge_point_id].title

        if effective_id in merged:
            if merged[effective_id].title != title:
                stats.knowledge_points_updated += 1
            merged[effective_id] = KnowledgePointDef(
                knowledge_point_id=effective_id,
                title=title,
            )
        else:
            stats.knowledge_points_added += 1
            merged[effective_id] = KnowledgePointDef(
                knowledge_point_id=effective_id,
                title=title,
            )

    for kp_id in list(merged.keys()):
        if kp_id in draft_kp_ids:
            continue
        missing_id = f"kp-missing:{draft_unit.unit_id}:{kp_id}"
        entry = resolutions.get(missing_id)
        if entry and entry.action == ResolutionAction.use_draft:
            del merged[kp_id]
            stats.knowledge_points_removed += 1
        else:
            stats.knowledge_points_kept += 1

    ordered = sorted(merged.values(), key=lambda k: k.knowledge_point_id)
    return ordered, stats


def merge_approved_draft(
    catalog: KpCatalog,
    draft: KpDocumentDraft,
    diff: CatalogDiff,
    resolutions: list[ConflictResolutionEntry],
) -> tuple[KpCatalog, CatalogMergeReport]:
    del diff  # merge is driven by draft + resolutions; diff kept for API symmetry
    res_map = _conflict_map(resolutions)
    report = CatalogMergeReport(job_id="")
    units_by_id = {u.unit_id: u.model_copy(deep=True) for u in catalog.units}

    for draft_unit in draft.units:
        existing = units_by_id.get(draft_unit.unit_id)
        if existing is None:
            kps: list[KnowledgePointDef] = []
            for draft_kp in draft_unit.knowledge_points:
                effective_id = _effective_kp_id(draft_kp.knowledge_point_id, res_map)
                if effective_id is None:
                    continue
                kps.append(
                    KnowledgePointDef(
                        knowledge_point_id=effective_id,
                        title=draft_kp.title,
                    )
                )
            units_by_id[draft_unit.unit_id] = UnitCatalogEntry(
                unit_id=draft_unit.unit_id,
                grade=draft.grade,
                subject=draft.subject,
                unit_title=draft_unit.unit_title,
                textbook_ref=draft.textbook_ref,
                knowledge_points=sorted(kps, key=lambda k: k.knowledge_point_id),
            )
            report.units_added.append(draft_unit.unit_id)
            report.knowledge_points_added += len(kps)
            continue

        merged_kps, unit_stats = _merge_unit_knowledge_points(existing, draft_unit, res_map)
        existing.unit_title = draft_unit.unit_title
        existing.textbook_ref = draft.textbook_ref
        existing.knowledge_points = merged_kps
        units_by_id[draft_unit.unit_id] = existing
        report.units_updated.append(draft_unit.unit_id)
        report.knowledge_points_added += unit_stats.knowledge_points_added
        report.knowledge_points_updated += unit_stats.knowledge_points_updated
        report.knowledge_points_removed += unit_stats.knowledge_points_removed
        report.knowledge_points_kept += unit_stats.knowledge_points_kept

    _assert_global_kp_ids_unique(list(units_by_id.values()))

    updated = KpCatalog(
        schema_version=catalog.schema_version,
        school_stage=catalog.school_stage,
        units=sorted(units_by_id.values(), key=lambda u: u.unit_id),
    )
    return updated, report


def _assert_global_kp_ids_unique(units: list[UnitCatalogEntry]) -> None:
    seen: dict[str, str] = {}
    for unit in units:
        for kp in unit.knowledge_points:
            if kp.knowledge_point_id in seen and seen[kp.knowledge_point_id] != unit.unit_id:
                raise ValueError(
                    f"duplicate knowledge_point_id {kp.knowledge_point_id!r} "
                    f"across units {seen[kp.knowledge_point_id]!r} and {unit.unit_id!r}"
                )
            seen[kp.knowledge_point_id] = unit.unit_id


class KpCatalogWriter:
    def __init__(
        self,
        catalog_svc: KpCatalogService,
        audit_dir: Optional[Path] = None,
    ) -> None:
        self._svc = catalog_svc
        self._path = catalog_svc._path  # noqa: SLF001
        if audit_dir is None:
            audit_dir = self._path.parent / "audit"
        self._audit_dir = Path(audit_dir)

    def save_with_backup(self, catalog: KpCatalog) -> Path:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d-%H%M%S")
        backup_path = self._path.with_name(f"{self._path.stem}.{ts}.bak.json")
        if self._path.is_file():
            shutil.copy2(self._path, backup_path)
        payload = catalog.model_dump(mode="json")
        self._path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        self._svc._catalog = KpCatalog.model_validate(payload)  # noqa: SLF001
        self._svc._by_unit = {u.unit_id: u for u in self._svc._catalog.units}  # noqa: SLF001
        return backup_path

    def write_audit_record(
        self,
        *,
        job_id: str,
        backup_path: Path,
        merge_report: CatalogMergeReport,
        source_path: str,
    ) -> Path:
        self._audit_dir.mkdir(parents=True, exist_ok=True)
        ts = utc_now().strftime("%Y%m%d-%H%M%S")
        audit_path = self._audit_dir / f"approve-{job_id}-{ts}.json"
        record = {
            "job_id": job_id,
            "approved_at": utc_now().isoformat(),
            "source_path": source_path,
            "catalog_path": str(self._path),
            "backup_path": str(backup_path),
            "merge_report": merge_report.model_dump(mode="json"),
        }
        audit_path.write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return audit_path
