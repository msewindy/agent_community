"""Direct ingest 部编版三年级语文上册 — catalog / wiki / classroom activities."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.classroom_activities import (
    classroom_blurb_for_unit,
    save_from_pending_exercises,
)
from agent_platform.learning.g3_textbook_common import pending_exercises
from agent_platform.learning.kp_catalog import KpCatalog, KpCatalogService, get_kp_catalog_service
from agent_platform.learning.kp_catalog_diff import CatalogDiff
from agent_platform.learning.kp_catalog_merge import KpCatalogWriter, merge_approved_draft
from agent_platform.learning.kp_document_parser import KpDocumentDraft
from agent_platform.learning.kp_wiki_sync import KpWikiSyncService
from agent_platform.learning.pep_g3_chinese_parser import (
    TEXTBOOK_REF,
    build_kp_document,
)
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.question_bank_ingest import import_draft_questions


def _default_pdf_path() -> Path:
    from agent_platform.learning.pep_g3_chinese_parser import _default_pdf_path as _p

    return _p()


@dataclass
class ChineseIngestReport:
    units_added: int = 0
    units_updated: int = 0
    units_removed: list[str] = field(default_factory=list)
    knowledge_points: int = 0
    wiki_pages_synced: int = 0
    questions_imported: int = 0
    classroom_activities: int = 0
    classroom_activities_path: Optional[str] = None
    catalog_backup: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "units_added": self.units_added,
            "units_updated": self.units_updated,
            "units_removed": self.units_removed,
            "knowledge_points": self.knowledge_points,
            "wiki_pages_synced": self.wiki_pages_synced,
            "questions_imported": self.questions_imported,
            "classroom_activities": self.classroom_activities,
            "classroom_activities_path": self.classroom_activities_path,
            "catalog_backup": self.catalog_backup,
            "warnings": self.warnings,
        }


def _strip_existing_g3_chinese(catalog: KpCatalog) -> tuple[KpCatalog, list[str]]:
    removed: list[str] = []
    units = []
    for u in catalog.units:
        if u.unit_id.startswith("chinese-g3-u"):
            removed.append(u.unit_id)
            continue
        units.append(u)
    return (
        KpCatalog(
            schema_version=catalog.schema_version,
            school_stage=catalog.school_stage,
            units=units,
        ),
        removed,
    )


def _delete_chinese_g3_questions(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM questions WHERE unit_id LIKE ?", ("chinese-g3-u%",))
        conn.commit()
        return cur.rowcount


def _questions_only_draft(draft: KpDocumentDraft) -> KpDocumentDraft:
    units = []
    for u in draft.units:
        if not u.questions:
            continue
        units.append(u.model_copy(update={"knowledge_points": []}))
    return draft.model_copy(update={"units": units})


def _kp_only_draft(draft: KpDocumentDraft) -> KpDocumentDraft:
    units = [u.model_copy(update={"questions": []}) for u in draft.units]
    return draft.model_copy(update={"units": units})


def _classroom_by_unit_from_path(act_path: Path) -> dict[int, list]:
    raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
    out: dict[int, list] = {}
    for u in raw_acts.get("units") or []:
        out[int(u["unit_num"])] = u.get("activities") or []
    return out


def run_pep_g3_chinese_ingest(
    *,
    textbook_path: Optional[Path] = None,
    catalog_svc: Optional[KpCatalogService] = None,
    data_root: Optional[Path] = None,
    job_id_prefix: str = "ing-pep-g3-chinese",
) -> ChineseIngestReport:
    textbook_path = textbook_path or _default_pdf_path()
    if not textbook_path.is_file():
        raise FileNotFoundError(f"chinese textbook PDF not found: {textbook_path}")

    report = ChineseIngestReport()
    draft, all_exercises = build_kp_document(textbook_path)
    kp_draft = _kp_only_draft(draft)

    catalog_svc = catalog_svc or get_kp_catalog_service()
    catalog, removed = _strip_existing_g3_chinese(catalog_svc.catalog)
    report.units_removed = removed

    diff = CatalogDiff(subject=kp_draft.subject, grade=kp_draft.grade, units=[], conflicts=[])
    merged, merge_report = merge_approved_draft(catalog, kp_draft, diff, [])
    report.units_added = len(merge_report.units_added)
    report.units_updated = len(merge_report.units_updated)
    report.knowledge_points = sum(len(u.knowledge_points) for u in kp_draft.units)

    cfg = load_student_learning_config()
    raw_root = (cfg.get("data") or {}).get("root", "student_data")
    audit_dir = (data_root or repo_root() / raw_root) / "_kp_catalog_audit"
    writer = KpCatalogWriter(catalog_svc, audit_dir=audit_dir)
    backup = writer.save_with_backup(merged)
    report.catalog_backup = str(backup)
    catalog_svc.reload()

    pending = pending_exercises(all_exercises)
    classroom_by_unit: dict[int, list] = {}
    if pending:
        act_path = save_from_pending_exercises(
            pending,
            data_root=data_root,
            textbook_ref=TEXTBOOK_REF,
            subject="语文",
            grade=3,
            slug="chinese-g3-pep",
        )
        raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
        report.classroom_activities = int(raw_acts.get("activity_count") or len(pending))
        report.classroom_activities_path = str(act_path)
        report.warnings.append(f"{len(pending)} 项语文课堂活动已记入 classroom_activities")
        classroom_by_unit = _classroom_by_unit_from_path(act_path)

    wiki = KpWikiSyncService(catalog=catalog_svc)
    desc_map: dict[str, str] = {}
    for unit in kp_draft.units:
        for kp in unit.knowledge_points:
            base = kp.description or ""
            if kp.knowledge_point_id.endswith("-reading"):
                try:
                    num = int(unit.unit_id.rsplit("u", 1)[-1])
                except ValueError:
                    num = 0
                acts = classroom_by_unit.get(num) or []
                if acts:
                    base = base + classroom_blurb_for_unit(num, acts)
            if base:
                desc_map[kp.knowledge_point_id] = base

    for unit in merged.units:
        if not unit.unit_id.startswith("chinese-g3-u"):
            continue
        unit_report = wiki.sync_unit_from_catalog(
            unit,
            descriptions=desc_map,
            source_job_id=job_id_prefix,
            force=True,
        )
        report.wiki_pages_synced += unit_report.pages_synced
        report.warnings.extend(unit_report.warnings)

    bank = QuestionBankService()
    _delete_chinese_g3_questions(bank.sqlite_path)

    auto_draft = _questions_only_draft(draft)
    if auto_draft.has_questions():
        try:
            q_result = import_draft_questions(auto_draft, source_path=textbook_path, archive=False)
            report.questions_imported = q_result.imported
            report.warnings.extend(q_result.warnings)
        except ValueError as exc:
            report.warnings.append(f"auto question import failed: {exc}")

    seed_path = repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_chinese_pep.json"
    _write_seed_json(auto_draft, seed_path)

    return report


def _write_seed_json(draft: KpDocumentDraft, path: Path) -> None:
    questions = []
    for q in draft.to_questions():
        questions.append(
            {
                "question_id": q.question_id,
                "unit_id": q.unit_id,
                "knowledge_point_id": q.knowledge_point_id,
                "expected_answer": q.expected_answer,
                "stem": q.stem,
                "answer_type": q.answer_type.value,
                "explanation": q.explanation,
                "default_error_code": q.default_error_code,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "subject": "语文",
        "grade": 3,
        "questions": questions,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
