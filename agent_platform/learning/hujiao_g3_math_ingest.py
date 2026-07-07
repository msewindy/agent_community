"""Direct ingest 沪教三年级数学上册 — catalog / wiki / question bank."""

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
from agent_platform.learning.hujiao_g3_math_parser import (
    TEXTBOOK_REF,
    build_kp_document,
)
from agent_platform.learning.kp_catalog import KpCatalog, KpCatalogService, get_kp_catalog_service
from agent_platform.learning.kp_catalog_diff import CatalogDiff
from agent_platform.learning.kp_catalog_merge import KpCatalogWriter, merge_approved_draft
from agent_platform.learning.kp_document_parser import KpDocumentDraft
from agent_platform.learning.kp_wiki_sync import KpWikiSyncService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.question_bank_ingest import import_draft_questions

LEGACY_UNIT_ID = "math-g3-mixed-ops"
LEGACY_KP_PREFIX = "kp-g3-mix-"
DEFAULT_TEXTBOOK = None  # resolved at runtime


def _default_pdf_path() -> Path:
    from agent_platform.learning.hujiao_g3_math_parser import _default_pdf_path as _p

    return _p()


@dataclass
class MathIngestReport:
    units_added: int = 0
    units_updated: int = 0
    units_removed: list[str] = field(default_factory=list)
    knowledge_points: int = 0
    wiki_pages_synced: int = 0
    questions_imported: int = 0
    questions_deleted: int = 0
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
            "questions_deleted": self.questions_deleted,
            "classroom_activities": self.classroom_activities,
            "classroom_activities_path": self.classroom_activities_path,
            "catalog_backup": self.catalog_backup,
            "warnings": self.warnings,
        }


def _strip_legacy_units(catalog: KpCatalog) -> tuple[KpCatalog, list[str]]:
    removed: list[str] = []
    units = []
    for u in catalog.units:
        if u.unit_id == LEGACY_UNIT_ID or u.unit_id.startswith("math-g3-u"):
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


def _delete_math_questions(db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute(
            "DELETE FROM questions WHERE unit_id = ? OR unit_id LIKE ?",
            (LEGACY_UNIT_ID, "math-g3-u%"),
        )
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


_CLASSROOM_BLURB_MARKER = "课堂活动（请在课堂完成"


def _classroom_by_unit_from_path(act_path: Path) -> dict[int, list]:
    raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
    out: dict[int, list] = {}
    for u in raw_acts.get("units") or []:
        out[int(u["unit_num"])] = u.get("activities") or []
    return out


LEGACY_KP_MAP = {
    "kp-g3-mix-mult-add": "kp-math-g3-u01-mult-add",
    "kp-g3-mix-mult-sub": "kp-math-g3-u01-mult-sub",
    "kp-g3-mix-div-add": "kp-math-g3-u01-div-add",
    "kp-g3-mix-div-sub": "kp-math-g3-u01-div-sub",
    "kp-g3-mix-same-level": "kp-math-g3-u01-same-level",
    "kp-g3-mix-parentheses": "kp-math-g3-u01-parentheses",
    "kp-g3-mix-word-problem": "kp-math-g3-u01-word-problem",
    "kp-g3-mix-expr-meaning": "kp-math-g3-u01-expr-meaning",
}


def _supplement_u01_questions(draft: KpDocumentDraft) -> None:
    """Merge legacy hand-authored u01 seed (dedupe by stem)."""
    from agent_platform.learning.contracts import AnswerType
    from agent_platform.learning.kp_document_parser import KpDocumentQuestion

    legacy = repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_math_mixed_ops.json"
    if not legacy.is_file() or not draft.units:
        return
    unit = draft.units[0]
    seen = {q.stem for q in unit.questions}
    data = json.loads(legacy.read_text(encoding="utf-8"))
    counter = len(unit.questions)
    for row in data.get("questions") or []:
        stem = row.get("stem") or ""
        if stem in seen:
            continue
        counter += 1
        kp = LEGACY_KP_MAP.get(row.get("knowledge_point_id", ""), row.get("knowledge_point_id"))
        unit.questions.append(
            KpDocumentQuestion(
                question_id=f"q-math-g3-u01-{counter:03d}",
                stem=stem,
                knowledge_point_id=kp,
                expected_answer=str(row.get("expected_answer")),
                explanation=str(row.get("explanation") or ""),
                default_error_code=str(row.get("default_error_code") or "PROCEDURE_ERROR"),
                answer_type=AnswerType(row.get("answer_type") or "exact"),
            )
        )
        seen.add(stem)


def run_hujiao_g3_math_ingest(
    *,
    textbook_path: Optional[Path] = None,
    catalog_svc: Optional[KpCatalogService] = None,
    data_root: Optional[Path] = None,
    job_id_prefix: str = "ing-hujiao-g3-math",
) -> MathIngestReport:
    textbook_path = textbook_path or _default_pdf_path()
    if not textbook_path.is_file():
        raise FileNotFoundError(f"math textbook PDF not found: {textbook_path}")

    report = MathIngestReport()
    draft, all_exercises = build_kp_document(textbook_path)
    _supplement_u01_questions(draft)
    kp_draft = _kp_only_draft(draft)

    catalog_svc = catalog_svc or get_kp_catalog_service()
    catalog, removed = _strip_legacy_units(catalog_svc.catalog)
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
            subject="数学",
            grade=3,
            slug="math-g3-hujiao",
        )
        raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
        report.classroom_activities = int(raw_acts.get("activity_count") or len(pending))
        report.classroom_activities_path = str(act_path)
        report.warnings.append(f"{len(pending)} 项数学课堂活动已记入 classroom_activities")
        classroom_by_unit = _classroom_by_unit_from_path(act_path)

    wiki = KpWikiSyncService(catalog=catalog_svc)
    desc_map: dict[str, str] = {}
    for unit in kp_draft.units:
        for kp in unit.knowledge_points:
            base = kp.description or ""
            if kp.knowledge_point_id.endswith("-reading") or kp.knowledge_point_id.endswith("-word-problem"):
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
        if not unit.unit_id.startswith("math-g3-u"):
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
    deleted = _delete_math_questions(bank.sqlite_path)
    report.questions_deleted = deleted
    if deleted:
        report.warnings.append(f"removed {deleted} legacy math question(s)")

    auto_draft = _questions_only_draft(draft)
    if auto_draft.has_questions():
        try:
            q_result = import_draft_questions(auto_draft, source_path=textbook_path, archive=False)
            report.questions_imported = q_result.imported
            report.warnings.extend(q_result.warnings)
        except ValueError as exc:
            report.warnings.append(f"auto question import failed: {exc}")

    seed_path = repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_math_hujiao.json"
    _write_seed_json(auto_draft, seed_path)

    _migrate_student_context_math_unit(data_root=data_root)

    return report


def _migrate_student_context_math_unit(*, data_root: Optional[Path] = None) -> None:
    """If context still on legacy math unit, move to math-g3-u01."""
    cfg = load_student_learning_config()
    raw_root = (cfg.get("data") or {}).get("root", "student_data")
    root = data_root or repo_root() / raw_root
    ctx_path = root / "g2-stu-01" / "context.json"
    if not ctx_path.is_file():
        return
    raw = json.loads(ctx_path.read_text(encoding="utf-8"))
    cur = raw.get("curriculum") or {}
    if cur.get("unit_id") != LEGACY_UNIT_ID:
        return
    cur["unit_id"] = "math-g3-u01"
    cur["unit_title"] = "两步四则运算与应用题"
    cur["textbook_ref"] = TEXTBOOK_REF
    raw["curriculum"] = cur
    ctx_path.write_text(json.dumps(raw, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_seed_json(draft: KpDocumentDraft, path: Path) -> None:
    questions = []
    for q in draft.to_questions():
        questions.append(
            {
                "question_id": q.question_id,
                "unit_id": q.unit_id,
                "knowledge_point_id": q.knowledge_point_id,
                "stem": q.stem,
                "answer_type": q.answer_type.value,
                "expected_answer": q.expected_answer,
                "explanation": q.explanation,
                "default_error_code": q.default_error_code,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "subject": "数学",
        "grade": 3,
        "questions": questions,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
