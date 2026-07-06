"""Validate and import practice questions from `.kp.md` drafts (P1-1)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.contracts import Question
from agent_platform.learning.kp_catalog import KpCatalogService, get_kp_catalog_service
from agent_platform.learning.kp_document_parser import KpDocumentDraft
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning import sqlite_store
from agent_platform.learning.taxonomy import TaxonomyService


@dataclass
class QuestionValidateResult:
    ok: bool
    question_count: int = 0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    overwrite_ids: list[str] = field(default_factory=list)
    unit_counts: dict[str, int] = field(default_factory=dict)


@dataclass
class QuestionImportResult:
    imported: int
    sqlite_path: str
    archive_path: Optional[str] = None
    warnings: list[str] = field(default_factory=list)


def uploads_dir() -> Path:
    return repo_root() / "agent_platform" / "learning" / "question_bank" / "uploads"


def _allowed_kp_ids(catalog: KpCatalogService, draft: KpDocumentDraft) -> set[str]:
    ids: set[str] = set()
    for unit in catalog.catalog.units:
        for kp in unit.knowledge_points:
            ids.add(kp.knowledge_point_id)
    for unit in draft.units:
        for kp in unit.knowledge_points:
            ids.add(kp.knowledge_point_id)
    return ids


def _allowed_unit_ids(catalog: KpCatalogService) -> set[str]:
    return {u.unit_id for u in catalog.catalog.units}


def validate_draft_questions(
    draft: KpDocumentDraft,
    *,
    catalog: Optional[KpCatalogService] = None,
    bank: Optional[QuestionBankService] = None,
    taxonomy: Optional[TaxonomyService] = None,
) -> QuestionValidateResult:
    catalog = catalog or get_kp_catalog_service()
    bank = bank or QuestionBankService()
    taxonomy = taxonomy or TaxonomyService()

    errors: list[str] = []
    warnings: list[str] = []
    overwrite_ids: list[str] = []
    unit_counts: dict[str, int] = {}

    if not draft.has_questions():
        return QuestionValidateResult(ok=True, question_count=0)

    allowed_kps = _allowed_kp_ids(catalog, draft)
    allowed_units = _allowed_unit_ids(catalog)
    existing_ids: set[str] = set()
    if bank.uses_sqlite:
        existing_ids = {q.question_id for q in bank.list_questions()}

    seen_ids: set[str] = set()
    count = 0

    for unit in draft.units:
        if not unit.questions:
            continue
        if draft.is_questions_only() and unit.unit_id not in allowed_units:
            errors.append(f"unit {unit.unit_id!r} not in catalog (questions-only upload)")
        unit_counts[unit.unit_id] = len(unit.questions)
        for q in unit.questions:
            count += 1
            if q.question_id in seen_ids:
                errors.append(f"duplicate question_id in document: {q.question_id}")
            seen_ids.add(q.question_id)
            if q.knowledge_point_id not in allowed_kps:
                errors.append(
                    f"{q.question_id}: knowledge_point_id {q.knowledge_point_id!r} not in catalog or draft"
                )
            try:
                taxonomy.lookup(q.default_error_code)
            except KeyError:
                errors.append(
                    f"{q.question_id}: unknown error_code {q.default_error_code!r}"
                )
            if q.expected_answer.strip() in {"", "TBD", "tbd", "待补", "待人工补全"}:
                errors.append(f"{q.question_id}: expected_answer is placeholder (TBD); fill in before import")
            if q.answer_type.value == "numeric" and q.numeric_tolerance is None:
                warnings.append(f"{q.question_id}: numeric type without 容差")
            if q.question_id in existing_ids:
                overwrite_ids.append(q.question_id)

    cfg = load_student_learning_config()
    min_q = int((cfg.get("seed") or {}).get("min_questions", 10))
    for unit_id, n in unit_counts.items():
        if n < min_q:
            warnings.append(f"unit {unit_id} has {n} questions (< recommended {min_q})")

    if overwrite_ids:
        warnings.append(
            f"{len(overwrite_ids)} question(s) will overwrite existing entries in SQLite"
        )

    return QuestionValidateResult(
        ok=not errors,
        question_count=count,
        errors=errors,
        warnings=warnings,
        overwrite_ids=overwrite_ids,
        unit_counts=unit_counts,
    )


def import_draft_questions(
    draft: KpDocumentDraft,
    *,
    bank: Optional[QuestionBankService] = None,
    source_path: Optional[str | Path] = None,
    archive: bool = True,
) -> QuestionImportResult:
    validation = validate_draft_questions(draft, bank=bank)
    if not validation.ok:
        raise ValueError("; ".join(validation.errors))
    if validation.question_count == 0:
        return QuestionImportResult(imported=0, sqlite_path="", warnings=validation.warnings)

    bank = bank or QuestionBankService()
    questions = draft.to_questions()
    sqlite_store.upsert_questions(bank.sqlite_path, questions)

    archive_path: Optional[str] = None
    if archive and source_path:
        src = Path(source_path)
        if src.is_file():
            archive_path = str(archive_kp_source(src))

    try:
        from agent_platform.integrations.hermes.student_tools import invalidate_question_bank_cache

        invalidate_question_bank_cache()
    except ImportError:
        pass

    return QuestionImportResult(
        imported=len(questions),
        sqlite_path=str(bank.sqlite_path),
        archive_path=archive_path,
        warnings=validation.warnings,
    )


def archive_kp_source(source_path: Path) -> Path:
    dest_dir = uploads_dir()
    dest_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    dest = dest_dir / f"{stamp}_{source_path.name}"
    shutil.copy2(source_path, dest)
    return dest


def question_bank_overview(*, bank: Optional[QuestionBankService] = None) -> dict:
    bank = bank or QuestionBankService()
    catalog = get_kp_catalog_service()
    by_unit: dict[str, int] = {}
    total = 0
    for q in bank.list_questions():
        by_unit[q.unit_id] = by_unit.get(q.unit_id, 0) + 1
        total += 1

    catalog_units = []
    for unit in catalog.catalog.units:
        catalog_units.append(
            {
                "unit_id": unit.unit_id,
                "unit_title": unit.unit_title,
                "subject": unit.subject,
                "grade": unit.grade,
                "question_count": by_unit.get(unit.unit_id, 0),
            }
        )

    orphan_units = [
        {"unit_id": uid, "question_count": n}
        for uid, n in sorted(by_unit.items())
        if uid not in {u.unit_id for u in catalog.catalog.units}
    ]

    return {
        "total_questions": total,
        "uses_sqlite": bank.uses_sqlite,
        "sqlite_path": str(bank.sqlite_path),
        "units": catalog_units,
        "orphan_units": orphan_units,
    }
