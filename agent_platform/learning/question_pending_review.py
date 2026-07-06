"""课本批量待审习题队列 — 走「习题处理」，不进「知识点入库」。"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from agent_platform.learning.kp_document_parser import KpDocumentDraft, KpDocumentQuestion
from agent_platform.learning.kp_ingest_review import KpIngestReviewService
from agent_platform.learning.question_bank_ingest import import_draft_questions, validate_draft_questions
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestJob, TextbookIngestService

REVIEW_QUEUE_FLAG = "review_queue"
QUESTION_BANK_QUEUE = "question_bank"
SOURCE_KEY_FLAG = "source_key"
PLACEHOLDER_ANSWERS = frozenset({"", "TBD", "tbd", "待补", "待人工补全"})
HUJIAO_PENDING_SOURCE_KEY = "hujiao-g3-english-pending"


def is_question_bank_queue(job: TextbookIngestJob) -> bool:
    flags = job.review_flags or {}
    if flags.get(REVIEW_QUEUE_FLAG) == QUESTION_BANK_QUEUE:
        return True
    draft = job.parsed_draft or {}
    if not draft:
        return False
    units = draft.get("units") or []
    has_kp = any(u.get("knowledge_points") for u in units)
    has_q = any(u.get("questions") for u in units)
    return has_q and not has_kp


def mark_question_bank_queue(
    job: TextbookIngestJob,
    *,
    source_key: Optional[str] = None,
) -> TextbookIngestJob:
    flags = dict(job.review_flags or {})
    flags[REVIEW_QUEUE_FLAG] = QUESTION_BANK_QUEUE
    if source_key:
        flags[SOURCE_KEY_FLAG] = source_key
    job.review_flags = flags
    return job


def list_question_pending_jobs(
    ingest_svc: TextbookIngestService,
    *,
    status: Optional[IngestJobStatus] = IngestJobStatus.pending_review,
) -> list[TextbookIngestJob]:
    jobs = ingest_svc.list_jobs(status=status)
    return [j for j in jobs if is_question_bank_queue(j)]


def flatten_job_questions(job: TextbookIngestJob) -> list[dict[str, Any]]:
    draft = KpDocumentDraft.model_validate(job.parsed_draft or {"subject": "", "grade": 1, "textbook_ref": ""})
    items: list[dict[str, Any]] = []
    for unit in draft.units:
        for q in unit.questions:
            items.append(
                {
                    "question_id": q.question_id,
                    "unit_id": unit.unit_id,
                    "unit_title": unit.unit_title,
                    "stem": q.stem,
                    "knowledge_point_id": q.knowledge_point_id,
                    "expected_answer": q.expected_answer,
                    "explanation": q.explanation,
                    "default_error_code": q.default_error_code,
                    "answer_type": q.answer_type.value,
                    "needs_answer": _needs_answer(q.expected_answer),
                }
            )
    return items


def _needs_answer(answer: str) -> bool:
    return answer.strip() in PLACEHOLDER_ANSWERS


def _draft_from_job(job: TextbookIngestJob) -> KpDocumentDraft:
    if not job.parsed_draft:
        raise ValueError(f"job {job.job_id} has no parsed_draft")
    return KpDocumentDraft.model_validate(job.parsed_draft)


def _save_draft(
    ingest_svc: TextbookIngestService,
    job: TextbookIngestJob,
    draft: KpDocumentDraft,
    *,
    review_svc: Optional[KpIngestReviewService] = None,
) -> TextbookIngestJob:
    job.parsed_draft = draft.model_dump(mode="json")
    review = review_svc or KpIngestReviewService(ingest_svc=ingest_svc)
    job = review.attach_review_to_job(job)
    ingest_svc._save(job)  # noqa: SLF001
    return job


def update_job_question(
    ingest_svc: TextbookIngestService,
    job_id: str,
    question_id: str,
    *,
    expected_answer: Optional[str] = None,
    knowledge_point_id: Optional[str] = None,
    explanation: Optional[str] = None,
) -> TextbookIngestJob:
    job = ingest_svc.get_job(job_id)
    if job.status != IngestJobStatus.pending_review:
        raise ValueError(f"job {job_id} is not pending_review")
    if not is_question_bank_queue(job):
        raise ValueError(f"job {job_id} is not a question-bank pending job")

    draft = _draft_from_job(job)
    found = False
    units = []
    for unit in draft.units:
        questions = []
        for q in unit.questions:
            if q.question_id != question_id:
                questions.append(q)
                continue
            found = True
            updates: dict[str, Any] = {}
            if expected_answer is not None:
                updates["expected_answer"] = expected_answer.strip()
            if knowledge_point_id is not None:
                updates["knowledge_point_id"] = knowledge_point_id.strip()
            if explanation is not None:
                updates["explanation"] = explanation.strip()
            questions.append(q.model_copy(update=updates))
        units.append(unit.model_copy(update={"questions": questions}))
    if not found:
        raise KeyError(f"question not found: {question_id}")

    return _save_draft(ingest_svc, job, draft.model_copy(update={"units": units}))


def drop_job_question(
    ingest_svc: TextbookIngestService,
    job_id: str,
    question_id: str,
) -> TextbookIngestJob:
    job = ingest_svc.get_job(job_id)
    if job.status != IngestJobStatus.pending_review:
        raise ValueError(f"job {job_id} is not pending_review")

    draft = _draft_from_job(job)
    found = False
    units = []
    for unit in draft.units:
        kept = [q for q in unit.questions if q.question_id != question_id]
        if len(kept) != len(unit.questions):
            found = True
        if kept:
            units.append(unit.model_copy(update={"questions": kept}))
    if not found:
        raise KeyError(f"question not found: {question_id}")

    draft = draft.model_copy(update={"units": units})
    job = _save_draft(ingest_svc, job, draft)
    if not draft.has_questions():
        job.status = IngestJobStatus.approved
        job.notes = list(job.notes) + ["all pending questions handled; job closed"]
        ingest_svc._save(job)  # noqa: SLF001
    return job


def import_ready_questions(
    ingest_svc: TextbookIngestService,
    job_id: str,
    *,
    question_ids: Optional[list[str]] = None,
) -> dict[str, Any]:
    """Import questions with valid answers; remove them from the pending job."""
    job = ingest_svc.get_job(job_id)
    if job.status != IngestJobStatus.pending_review:
        raise ValueError(f"job {job_id} is not pending_review")

    draft = _draft_from_job(job)
    imported_ids: list[str] = []
    skipped: list[dict[str, str]] = []
    import_units = []
    remain_units = []

    for unit in draft.units:
        to_import: list[KpDocumentQuestion] = []
        to_remain: list[KpDocumentQuestion] = []
        for q in unit.questions:
            if question_ids is not None and q.question_id not in question_ids:
                to_remain.append(q)
                continue
            if _needs_answer(q.expected_answer):
                skipped.append({"question_id": q.question_id, "reason": "答案未补全"})
                to_remain.append(q)
                continue
            single = KpDocumentDraft(
                subject=draft.subject,
                grade=draft.grade,
                textbook_ref=draft.textbook_ref,
                units=[unit.model_copy(update={"questions": [q], "knowledge_points": []})],
            )
            v = validate_draft_questions(single)
            if not v.ok:
                skipped.append({"question_id": q.question_id, "reason": "; ".join(v.errors)})
                to_remain.append(q)
                continue
            to_import.append(q)
            imported_ids.append(q.question_id)

        if to_import:
            import_units.append(unit.model_copy(update={"questions": to_import, "knowledge_points": []}))
        if to_remain:
            remain_units.append(unit.model_copy(update={"questions": to_remain}))

    if not imported_ids:
        return {"imported": 0, "imported_ids": [], "skipped": skipped, "remaining": draft.question_count}

    import_draft = draft.model_copy(update={"units": import_units})
    result = import_draft_questions(import_draft, source_path=job.source_path, archive=False)

    job = _save_draft(ingest_svc, job, draft.model_copy(update={"units": remain_units}))
    if not remain_units:
        job.status = IngestJobStatus.approved
        job.notes = list(job.notes) + [f"imported {len(imported_ids)} question(s); job closed"]
        ingest_svc._save(job)  # noqa: SLF001

    return {
        "imported": result.imported,
        "imported_ids": imported_ids,
        "skipped": skipped,
        "remaining": sum(len(u.questions) for u in remain_units),
        "warnings": result.warnings,
    }


def upsert_question_pending_job(
    ingest_svc: TextbookIngestService,
    draft: KpDocumentDraft,
    source_path: str,
    *,
    source_key: str,
    notes: Optional[list[str]] = None,
) -> TextbookIngestJob:
    """Create or replace a question-bank pending job (dedupe by source_key)."""
    if not draft.is_questions_only():
        raise ValueError("upsert_question_pending_job requires a questions-only draft")

    existing = None
    for job in list_question_pending_jobs(ingest_svc):
        if (job.review_flags or {}).get(SOURCE_KEY_FLAG) == source_key:
            existing = job
            break

    if existing is not None:
        existing.parsed_draft = draft.model_dump(mode="json")
        existing.source_path = source_path
        existing.notes = list(existing.notes) + (notes or [])
        mark_question_bank_queue(existing, source_key=source_key)
        review = KpIngestReviewService(ingest_svc=ingest_svc)
        existing = review.attach_review_to_job(existing)
        ingest_svc._save(existing)  # noqa: SLF001
        return existing

    job = ingest_svc.submit_kp_document(source_path)
    job.parsed_draft = draft.model_dump(mode="json")
    job.notes = list(job.notes) + (notes or [])
    mark_question_bank_queue(job, source_key=source_key)
    review = KpIngestReviewService(ingest_svc=ingest_svc)
    job = review.attach_review_to_job(job)
    ingest_svc._save(job)  # noqa: SLF001
    return job


def dedupe_question_pending_jobs(
    ingest_svc: TextbookIngestService,
    *,
    review_svc: Optional[KpIngestReviewService] = None,
) -> dict[str, Any]:
    """Keep newest pending job per source_key; reject older duplicates."""
    review = review_svc or KpIngestReviewService(ingest_svc=ingest_svc)

    for job in ingest_svc.list_jobs(status=IngestJobStatus.pending_review):
        if is_question_bank_queue(job):
            mark_question_bank_queue(job)
            name = Path(job.source_path).name
            flags = job.review_flags or {}
            if SOURCE_KEY_FLAG not in flags and ("沪教" in name or "待审习题" in name):
                mark_question_bank_queue(job, source_key=HUJIAO_PENDING_SOURCE_KEY)
            ingest_svc._save(job)  # noqa: SLF001

    by_key: dict[str, list[TextbookIngestJob]] = {}
    for job in list_question_pending_jobs(ingest_svc):
        key = (job.review_flags or {}).get(SOURCE_KEY_FLAG) or job.source_path
        by_key.setdefault(key, []).append(job)

    kept: list[str] = []
    rejected: list[str] = []
    for key, jobs in by_key.items():
        ordered = sorted(jobs, key=lambda j: j.created_at, reverse=True)
        kept.append(ordered[0].job_id)
        for dup in ordered[1:]:
            review.reject(dup.job_id, reason=f"duplicate of {ordered[0].job_id} ({key})")
            rejected.append(dup.job_id)

    # Jobs without source_key but same display name — keep newest only
    unnamed = [
        j
        for j in list_question_pending_jobs(ingest_svc)
        if SOURCE_KEY_FLAG not in (j.review_flags or {})
    ]
    if len(unnamed) > 1:
        ordered = sorted(unnamed, key=lambda j: j.created_at, reverse=True)
        for dup in ordered[1:]:
            if dup.job_id not in rejected:
                review.reject(dup.job_id, reason=f"duplicate unnamed job; kept {ordered[0].job_id}")
                rejected.append(dup.job_id)

    return {"kept": kept, "rejected": rejected}
