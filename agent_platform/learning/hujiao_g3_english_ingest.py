"""Direct ingest 沪教三年级英语上册 — KP/wiki 直写，习题分流（明确/待审）。"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.hujiao_g3_english_parser import (
    AUTO_IMPORT_CONFIDENCE,
    TEXTBOOK_REF,
    build_kp_document,
    pending_exercises,
)
from agent_platform.learning.kp_catalog import KpCatalog, KpCatalogService, get_kp_catalog_service
from agent_platform.learning.kp_catalog_diff import CatalogDiff
from agent_platform.learning.kp_catalog_merge import CatalogMergeReport, KpCatalogWriter, merge_approved_draft
from agent_platform.learning.kp_document_parser import KpDocumentDraft
from agent_platform.learning.kp_wiki_sync import KpWikiSyncService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.question_bank_ingest import import_draft_questions
from agent_platform.learning.classroom_activities import (
    classroom_blurb_for_unit,
    save_from_pending_exercises,
)

REMOVED_STARTER_UNIT = "english-g3-starter"
DEFAULT_SUMMARY = repo_root() / "三年级课本" / "2026沪教新版三年级英语上册汇总.pdf"
DEFAULT_TEXTBOOK = (
    repo_root() / "三年级课本" / "义务教育教科书（五·四学制）_英语_三年级_上册(1).pdf"
)


@dataclass
class ClassroomSyncReport:
    classroom_activities: int = 0
    classroom_activities_path: Optional[str] = None
    wiki_reading_synced: int = 0
    wiki_reading_skipped: int = 0
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "classroom_activities": self.classroom_activities,
            "classroom_activities_path": self.classroom_activities_path,
            "wiki_reading_synced": self.wiki_reading_synced,
            "wiki_reading_skipped": self.wiki_reading_skipped,
            "warnings": self.warnings,
        }


@dataclass
class HujiaoIngestReport:
    units_added: int = 0
    units_removed: list[str] = field(default_factory=list)
    knowledge_points: int = 0
    wiki_pages_synced: int = 0
    questions_imported: int = 0
    questions_pending_review: int = 0
    classroom_activities: int = 0
    classroom_activities_path: Optional[str] = None
    catalog_backup: Optional[str] = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "units_added": self.units_added,
            "units_removed": self.units_removed,
            "knowledge_points": self.knowledge_points,
            "wiki_pages_synced": self.wiki_pages_synced,
            "questions_imported": self.questions_imported,
            "questions_pending_review": self.questions_pending_review,
            "classroom_activities": self.classroom_activities,
            "classroom_activities_path": self.classroom_activities_path,
            "catalog_backup": self.catalog_backup,
            "warnings": self.warnings,
        }


def _default_pdf_paths() -> tuple[Path, Path]:
    summary = DEFAULT_SUMMARY
    textbook = DEFAULT_TEXTBOOK
    if not summary.is_file():
        base = repo_root() / "三年级课本"
        hits = list(base.glob("*汇总*.pdf"))
        if hits:
            summary = hits[0]
    if not textbook.is_file():
        base = repo_root() / "三年级课本"
        hits = [p for p in base.glob("*.pdf") if "义务教育" in p.name or "三年级_上册" in p.name]
        if hits:
            textbook = hits[0]
    return summary, textbook


def _remove_starter_unit(catalog: KpCatalog) -> KpCatalog:
    units = [u for u in catalog.units if u.unit_id != REMOVED_STARTER_UNIT]
    return KpCatalog(
        schema_version=catalog.schema_version,
        school_stage=catalog.school_stage,
        units=units,
    )


def _delete_unit_questions(unit_id: str, db_path: Path) -> int:
    if not db_path.is_file():
        return 0
    with sqlite3.connect(db_path) as conn:
        cur = conn.execute("DELETE FROM questions WHERE unit_id = ?", (unit_id,))
        conn.commit()
        return cur.rowcount


def _questions_only_draft(draft: KpDocumentDraft) -> KpDocumentDraft:
    units = []
    for u in draft.units:
        if not u.questions:
            continue
        units.append(
            u.model_copy(update={"knowledge_points": []}),
        )
    return draft.model_copy(update={"units": units})


def _kp_only_draft(draft: KpDocumentDraft) -> KpDocumentDraft:
    units = []
    for u in draft.units:
        units.append(u.model_copy(update={"questions": []}))
    return draft.model_copy(update={"units": units})


_CLASSROOM_BLURB_MARKER = "课堂活动（请在课堂完成"


def _classroom_by_unit_from_path(act_path: Path) -> dict[int, list]:
    raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
    out: dict[int, list] = {}
    for u in raw_acts.get("units") or []:
        out[int(u["unit_num"])] = u.get("activities") or []
    return out


def run_classroom_activities_sync_only(
    *,
    summary_path: Optional[Path] = None,
    textbook_path: Optional[Path] = None,
    data_root: Optional[Path] = None,
    patch_wiki: bool = True,
    job_id_prefix: str = "sync-classroom-hujiao-g3",
) -> ClassroomSyncReport:
    """仅生成课堂活动清单，并可选地为 reading KP 补 Wiki 说明；不写 catalog / 题库。"""
    summary_path, textbook_path = summary_path or _default_pdf_paths()[0], textbook_path or _default_pdf_paths()[1]
    if not summary_path.is_file():
        raise FileNotFoundError(f"summary PDF not found: {summary_path}")
    if not textbook_path.is_file():
        raise FileNotFoundError(f"textbook PDF not found: {textbook_path}")

    report = ClassroomSyncReport()
    draft, all_exercises = build_kp_document(summary_path, textbook_path)
    kp_draft = _kp_only_draft(draft)
    pending = pending_exercises(all_exercises)
    if not pending:
        report.warnings.append("未解析到待课堂活动项，跳过写入")
        return report

    act_path = save_from_pending_exercises(
        pending,
        data_root=data_root,
        textbook_ref=TEXTBOOK_REF,
    )
    raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
    report.classroom_activities = int(raw_acts.get("activity_count") or len(pending))
    report.classroom_activities_path = str(act_path)
    report.warnings.append(
        f"{len(pending)} 项课本课堂活动已记入 classroom_activities（未改动 catalog / 题库）"
    )
    classroom_by_unit = _classroom_by_unit_from_path(act_path)

    if not patch_wiki:
        return report

    catalog_svc = get_kp_catalog_service()
    wiki = KpWikiSyncService(catalog=catalog_svc)
    desc_by_kp: dict[str, str] = {}
    for unit in kp_draft.units:
        for kp in unit.knowledge_points:
            if not kp.knowledge_point_id.endswith("-reading"):
                continue
            num = int(unit.unit_id.rsplit("u", 1)[-1])
            acts = classroom_by_unit.get(num) or []
            base = kp.description or ""
            if acts:
                base = base + classroom_blurb_for_unit(num, acts)
            if base:
                desc_by_kp[kp.knowledge_point_id] = base

    for unit in catalog_svc.catalog.units:
        if not unit.unit_id.startswith("english-g3-u"):
            continue
        for kp in unit.knowledge_points:
            if not kp.knowledge_point_id.endswith("-reading"):
                continue
            description = desc_by_kp.get(kp.knowledge_point_id)
            if not description:
                report.wiki_reading_skipped += 1
                continue
            raw_path = wiki.raw_path_for_kp(kp.knowledge_point_id)
            if raw_path.is_file():
                existing = raw_path.read_text(encoding="utf-8")
                if _CLASSROOM_BLURB_MARKER in existing:
                    report.wiki_reading_skipped += 1
                    continue
            try:
                page = wiki.sync_knowledge_point(
                    unit=unit,
                    kp=kp,
                    description=description,
                    source_job_id=job_id_prefix,
                    force=True,
                )
            except Exception as exc:  # noqa: BLE001
                report.warnings.append(f"{kp.knowledge_point_id}: {exc}")
                continue
            if page:
                report.wiki_reading_synced += 1
            else:
                report.wiki_reading_skipped += 1
    return report


def run_hujiao_g3_english_ingest(
    *,
    summary_path: Optional[Path] = None,
    textbook_path: Optional[Path] = None,
    catalog_svc: Optional[KpCatalogService] = None,
    data_root: Optional[Path] = None,
    job_id_prefix: str = "ing-hujiao-g3",
) -> HujiaoIngestReport:
    summary_path, textbook_path = summary_path or _default_pdf_paths()[0], textbook_path or _default_pdf_paths()[1]
    if not summary_path.is_file():
        raise FileNotFoundError(f"summary PDF not found: {summary_path}")
    if not textbook_path.is_file():
        raise FileNotFoundError(f"textbook PDF not found: {textbook_path}")

    report = HujiaoIngestReport()
    draft, all_exercises = build_kp_document(summary_path, textbook_path)
    kp_draft = _kp_only_draft(draft)

    catalog_svc = catalog_svc or get_kp_catalog_service()
    catalog = _remove_starter_unit(catalog_svc.catalog)
    if REMOVED_STARTER_UNIT in {u.unit_id for u in catalog_svc.catalog.units}:
        report.units_removed.append(REMOVED_STARTER_UNIT)

    diff = CatalogDiff(subject=kp_draft.subject, grade=kp_draft.grade, units=[], conflicts=[])
    merged, merge_report = merge_approved_draft(catalog, kp_draft, diff, [])
    report.units_added = len(merge_report.units_added)
    report.knowledge_points = sum(len(u.knowledge_points) for u in kp_draft.units)

    cfg = load_student_learning_config()
    raw_root = (cfg.get("data") or {}).get("root", "student_data")
    audit_dir = (data_root or repo_root() / raw_root) / "_kp_catalog_audit"
    writer = KpCatalogWriter(catalog_svc, audit_dir=audit_dir)
    backup = writer.save_with_backup(merged)
    report.catalog_backup = str(backup)
    catalog_svc.reload()

    wiki = KpWikiSyncService(catalog=catalog_svc)
    desc_map: dict[str, str] = {}
    classroom_by_unit: dict[int, list] = {}
    pending = pending_exercises(all_exercises)
    report.questions_pending_review = len(pending)
    if pending:
        act_path = save_from_pending_exercises(
            pending,
            data_root=data_root,
            textbook_ref=TEXTBOOK_REF,
        )
        raw_acts = json.loads(act_path.read_text(encoding="utf-8"))
        report.classroom_activities = int(raw_acts.get("activity_count") or len(pending))
        report.classroom_activities_path = str(act_path)
        report.warnings.append(
            f"{len(pending)} 项课本课堂活动已记入 classroom_activities（Jarvis 不推题，不进待归类）"
        )
        classroom_by_unit = _classroom_by_unit_from_path(act_path)

    for unit in kp_draft.units:
        for kp in unit.knowledge_points:
            base = kp.description or ""
            if kp.knowledge_point_id.endswith("-reading"):
                num = int(unit.unit_id.rsplit("u", 1)[-1])
                acts = classroom_by_unit.get(num) or []
                if acts:
                    base = base + classroom_blurb_for_unit(num, acts)
            if base:
                desc_map[kp.knowledge_point_id] = base
    for unit in merged.units:
        if not unit.unit_id.startswith("english-g3-u"):
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
    removed = _delete_unit_questions(REMOVED_STARTER_UNIT, bank.sqlite_path)
    if removed:
        report.warnings.append(f"removed {removed} starter question(s) from SQLite")

    auto_draft = _questions_only_draft(draft)
    if auto_draft.has_questions():
        try:
            q_result = import_draft_questions(auto_draft, source_path=summary_path, archive=False)
            report.questions_imported = q_result.imported
            report.warnings.extend(q_result.warnings)
        except ValueError as exc:
            report.warnings.append(f"auto question import failed: {exc}")

    seed_path = repo_root() / "agent_platform/learning/question_bank/seed_questions_g3_english_hujiao.json"
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
                "stem": q.stem,
                "answer_type": q.answer_type.value,
                "expected_answer": q.expected_answer,
                "explanation": q.explanation,
                "default_error_code": q.default_error_code,
            }
        )
    payload = {
        "schema_version": "1.0.0",
        "unit_id": "english-g3-u01",
        "grade": 3,
        "subject": "英语",
        "questions": questions,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_pending_kp_md(draft: KpDocumentDraft, data_root: Path) -> Path:
    out_dir = data_root / "_textbook_ingest" / "generated"
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / "英语-三年级-沪教-待审习题.kp.md"
    lines = [
        "---",
        f"学科: {draft.subject}",
        f"年级: {draft.grade}",
        f"教材版本: {draft.textbook_ref}",
        "文档说明: 课本图片/听力类习题，待人工补全答案与知识点关联",
        "---",
        "",
    ]
    for unit in draft.units:
        lines.append(f"# 单元：{unit.unit_title}（待审习题）")
        lines.append("")
        lines.append(f"unit_id: {unit.unit_id}")
        lines.append(f"教材章节: {unit.textbook_chapter}")
        lines.append("单元说明: 待审习题批次，批准前请逐题核对")
        lines.append("")
        lines.append("## 练习题")
        lines.append("")
        for q in unit.questions:
            lines.append(f"- {q.stem} → {q.question_id}")
            lines.append(f"  知识点: {q.knowledge_point_id}")
            lines.append(f"  答案: {q.expected_answer}")
            lines.append(f"  题型: {q.answer_type.value}")
            lines.append(f"  解析: {q.explanation}")
            lines.append(f"  错因: {q.default_error_code}")
            lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path
