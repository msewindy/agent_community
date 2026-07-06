"""Sync KP catalog entries into LLM Wiki for teaching (P1-4)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
from uuid import uuid4

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.kp_catalog import KpCatalogService, KnowledgePointDef, UnitCatalogEntry, get_kp_catalog_service
from agent_platform.learning.kp_catalog_merge import CatalogMergeReport
from agent_platform.learning.kp_document_parser import KpDocumentDraft, KpDocumentKp, KpDocumentUnit
from agent_platform.wiki._config import load_wiki_config, resolve_store_root
from agent_platform.wiki.contracts import WikiIngestRequest, WikiQueryRequest
from agent_platform.wiki.ingest import ingest_one
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import WikiStoreLayout, ensure_store


@dataclass
class KpWikiSyncReport:
    pages_synced: int = 0
    page_paths: list[str] = field(default_factory=list)
    skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "pages_synced": self.pages_synced,
            "page_paths": self.page_paths,
            "skipped": self.skipped,
            "warnings": self.warnings,
        }


def load_kp_wiki_config(config: Optional[dict] = None) -> dict:
    cfg = config or load_student_learning_config()
    raw = cfg.get("kp_wiki") or {}
    return {
        "enabled": bool(raw.get("enabled", True)),
        "sync_on_approve": bool(raw.get("sync_on_approve", True)),
        "bootstrap_pilot_units": bool(raw.get("bootstrap_pilot_units", True)),
    }


def _kp_description_map(draft: KpDocumentDraft) -> dict[str, str]:
    out: dict[str, str] = {}
    for unit in draft.units:
        for kp in unit.knowledge_points:
            if kp.description:
                out[kp.knowledge_point_id] = kp.description.strip()
    return out


def render_kp_wiki_markdown(
    *,
    kp: KnowledgePointDef,
    unit: UnitCatalogEntry,
    description: Optional[str] = None,
    source_job_id: Optional[str] = None,
) -> str:
    lines = [
        f"# {kp.title}",
        "",
        f"knowledge_point_id: {kp.knowledge_point_id}",
        f"unit_id: {unit.unit_id}",
        f"subject: {unit.subject}",
        f"grade: {unit.grade}",
        "",
        "## 讲解要点",
        "",
    ]
    if description:
        lines.append(description)
    else:
        lines.append(
            "（待补充：可在 `.kp.md` 知识点下写 `说明：…`，批准入库后会同步到此页。）"
        )
    lines.extend(
        [
            "",
            "## 教学提示",
            "",
            f"- 面向小学 {unit.grade} 年级「{unit.subject}」单元「{unit.unit_title}」。",
            "- 用短句、分步讲解；一次只讲一小步。",
            "- 无把握时不要假装「教材就是这样写的」。",
        ]
    )
    if source_job_id:
        lines.extend(["", f"source_job_id: {source_job_id}"])
    return "\n".join(lines) + "\n"


def find_kp_in_catalog(
    catalog: KpCatalogService,
    knowledge_point_id: str,
) -> tuple[UnitCatalogEntry, KnowledgePointDef] | None:
    for unit in catalog.catalog.units:
        for kp in unit.knowledge_points:
            if kp.knowledge_point_id == knowledge_point_id:
                return unit, kp
    return None


class KpWikiSyncService:
    def __init__(
        self,
        *,
        catalog: Optional[KpCatalogService] = None,
        wiki: Optional[WikiService] = None,
        config: Optional[dict] = None,
        store_root: Optional[Path] = None,
    ) -> None:
        self._cfg = load_kp_wiki_config(config)
        self._catalog = catalog or get_kp_catalog_service(config=config)
        if wiki is not None:
            self._wiki = wiki
            self._layout = wiki._layout  # noqa: SLF001
        else:
            wiki_cfg = load_wiki_config()
            root = store_root
            if root is None:
                raw_root = (config or load_student_learning_config()).get("kp_wiki") or {}
                store_raw = raw_root.get("store_root") if isinstance(raw_root, dict) else None
                if store_raw:
                    root = Path(store_raw)
                    if not root.is_absolute():
                        root = repo_root() / root
            root = root or resolve_store_root(wiki_cfg)
            self._layout = ensure_store(root)
            self._wiki = WikiService(config=wiki_cfg, layout=self._layout)

    @property
    def layout(self) -> WikiStoreLayout:
        return self._layout

    def raw_path_for_kp(self, knowledge_point_id: str) -> Path:
        return self._layout.root / "raw" / "kp" / f"{knowledge_point_id}.md"

    def sync_knowledge_point(
        self,
        *,
        unit: UnitCatalogEntry,
        kp: KnowledgePointDef,
        description: Optional[str] = None,
        source_job_id: Optional[str] = None,
        force: bool = False,
    ) -> Optional[str]:
        if not self._cfg["enabled"]:
            return None
        raw_path = self.raw_path_for_kp(kp.knowledge_point_id)
        if raw_path.is_file() and not force:
            return None
        raw_path.parent.mkdir(parents=True, exist_ok=True)
        body = render_kp_wiki_markdown(
            kp=kp,
            unit=unit,
            description=description,
            source_job_id=source_job_id,
        )
        raw_path.write_text(body, encoding="utf-8")
        raw_rel = raw_path.relative_to(self._layout.root).as_posix()
        ref = ingest_one(
            WikiIngestRequest(
                source_path=raw_rel,
                topic=kp.title,
                trace_id=source_job_id or str(uuid4()),
                metadata={"knowledge_point_id": kp.knowledge_point_id, "unit_id": unit.unit_id},
            ),
            self._layout,
        )
        return ref.path

    def sync_unit_from_catalog(
        self,
        unit: UnitCatalogEntry,
        *,
        descriptions: Optional[dict[str, str]] = None,
        source_job_id: Optional[str] = None,
        force: bool = False,
    ) -> KpWikiSyncReport:
        report = KpWikiSyncReport()
        desc_map = descriptions or {}
        for kp in unit.knowledge_points:
            try:
                page = self.sync_knowledge_point(
                    unit=unit,
                    kp=kp,
                    description=desc_map.get(kp.knowledge_point_id),
                    source_job_id=source_job_id,
                    force=force,
                )
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"{kp.knowledge_point_id}: {exc}")
                continue
            if page:
                report.pages_synced += 1
                report.page_paths.append(page)
            else:
                report.skipped += 1
        return report

    def sync_draft_after_approve(
        self,
        draft: KpDocumentDraft,
        merge_report: CatalogMergeReport,
        *,
        job_id: str,
    ) -> KpWikiSyncReport:
        if not self._cfg["enabled"] or not self._cfg["sync_on_approve"]:
            return KpWikiSyncReport()
        if not draft.has_knowledge_points():
            return KpWikiSyncReport()

        touched_units = set(merge_report.units_added) | set(merge_report.units_updated)
        desc_map = _kp_description_map(draft)
        report = KpWikiSyncReport()

        for draft_unit in draft.units:
            if touched_units and draft_unit.unit_id not in touched_units:
                continue
            try:
                catalog_unit = self._catalog.get_unit(draft_unit.unit_id)
            except KeyError:
                report.warnings.append(f"unit {draft_unit.unit_id} not in catalog after merge")
                continue
            unit_report = self._sync_draft_unit(
                catalog_unit,
                draft_unit,
                desc_map=desc_map,
                job_id=job_id,
            )
            report.pages_synced += unit_report.pages_synced
            report.page_paths.extend(unit_report.page_paths)
            report.skipped += unit_report.skipped
            report.warnings.extend(unit_report.warnings)
        return report

    def _sync_draft_unit(
        self,
        catalog_unit: UnitCatalogEntry,
        draft_unit: KpDocumentUnit,
        *,
        desc_map: dict[str, str],
        job_id: str,
    ) -> KpWikiSyncReport:
        report = KpWikiSyncReport()
        draft_by_id = {kp.knowledge_point_id: kp for kp in draft_unit.knowledge_points}
        for kp in catalog_unit.knowledge_points:
            draft_kp: Optional[KpDocumentKp] = draft_by_id.get(kp.knowledge_point_id)
            description = desc_map.get(kp.knowledge_point_id)
            if draft_kp and draft_kp.description and not description:
                description = draft_kp.description
            try:
                page = self.sync_knowledge_point(
                    unit=catalog_unit,
                    kp=kp,
                    description=description,
                    source_job_id=job_id,
                    force=True,
                )
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"{kp.knowledge_point_id}: {exc}")
                continue
            if page:
                report.pages_synced += 1
                report.page_paths.append(page)
            else:
                report.skipped += 1
        return report

    def bootstrap_pilot_units(self, config: Optional[dict] = None) -> KpWikiSyncReport:
        if not self._cfg["enabled"] or not self._cfg["bootstrap_pilot_units"]:
            return KpWikiSyncReport()
        cfg = config or load_student_learning_config()
        pilot_units = list((cfg.get("seed") or {}).get("pilot_units") or [])
        if not pilot_units:
            pilot = (cfg.get("pilot") or {}).get("units") or {}
            pilot_units = list(pilot.values())
        report = KpWikiSyncReport()
        for unit_id in pilot_units:
            try:
                unit = self._catalog.get_unit(unit_id)
            except KeyError:
                report.warnings.append(f"pilot unit missing from catalog: {unit_id}")
                continue
            unit_report = self.sync_unit_from_catalog(unit, force=False)
            report.pages_synced += unit_report.pages_synced
            report.page_paths.extend(unit_report.page_paths)
            report.skipped += unit_report.skipped
            report.warnings.extend(unit_report.warnings)
        return report

    def fetch_teaching_context(self, knowledge_point_id: str) -> dict:
        found = find_kp_in_catalog(self._catalog, knowledge_point_id)
        if found is None:
            return {
                "success": False,
                "error": f"knowledge_point_id not in catalog: {knowledge_point_id}",
            }
        unit, kp = found
        query = WikiQueryRequest(query=knowledge_point_id, limit=3)
        wiki_result = self._wiki.query(query)
        hits = [
            {
                "path": h.path,
                "title": h.title,
                "summary": h.summary,
            }
            for h in wiki_result.hits
        ]
        has_wiki = bool(hits) or bool(wiki_result.answer)
        return {
            "success": True,
            "knowledge_point_id": kp.knowledge_point_id,
            "title": kp.title,
            "unit_id": unit.unit_id,
            "unit_title": unit.unit_title,
            "subject": unit.subject,
            "grade": unit.grade,
            "has_wiki": has_wiki,
            "wiki_hits": hits,
            "wiki_answer": wiki_result.answer,
            "teaching_note": (
                "有 Wiki 讲解要点时，请据此分步讲解；"
                "若无 Wiki，诚实说明教案尚在补充，结合标题与单元上下文讲解，勿假装教材原文。"
            ),
        }


def bootstrap_pilot_kp_wiki(
    *,
    catalog: Optional[KpCatalogService] = None,
    store_root: Optional[Path] = None,
    config: Optional[dict] = None,
) -> KpWikiSyncReport:
    svc = KpWikiSyncService(catalog=catalog, store_root=store_root, config=config)
    return svc.bootstrap_pilot_units(config=config)
