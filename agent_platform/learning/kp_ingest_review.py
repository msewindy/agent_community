"""Ingest job review — checklist, conflict resolutions (P1-B)."""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from agent_platform.learning.contracts import utc_now
from agent_platform.learning.kp_catalog import KpCatalogService, get_kp_catalog_service
from agent_platform.learning.kp_catalog_diff import CatalogDiff, ConflictKind
from agent_platform.learning.kp_document_parser import KpDocumentDraft
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestJob, TextbookIngestService


class ResolutionAction(str, Enum):
    skip = "skip"
    use_draft = "use_draft"
    use_catalog = "use_catalog"
    rename_draft = "rename_draft"


class ConflictResolutionEntry(BaseModel):
    conflict_id: str
    action: ResolutionAction
    new_knowledge_point_id: Optional[str] = None
    note: Optional[str] = None


class ReviewChecklistItem(BaseModel):
    rule_id: str
    title: str
    required: bool = True
    satisfied: bool = False
    detail: Optional[str] = None
    action_hint: Optional[str] = None


class IngestReviewSnapshot(BaseModel):
    catalog_diff: CatalogDiff
    checklist: list[ReviewChecklistItem] = Field(default_factory=list)
    conflict_resolutions: list[ConflictResolutionEntry] = Field(default_factory=list)
    confirm_subject_grade: bool = False
    confirm_write: bool = False
    ready_to_approve: bool = False
    blocking_unresolved: int = 0


_ALLOWED_ACTIONS: dict[ConflictKind, set[ResolutionAction]] = {
    ConflictKind.kp_title_mismatch: {
        ResolutionAction.use_draft,
        ResolutionAction.use_catalog,
    },
    ConflictKind.kp_missing_in_draft: {
        ResolutionAction.use_catalog,
        ResolutionAction.use_draft,
    },
    ConflictKind.kp_cross_unit: {
        ResolutionAction.skip,
        ResolutionAction.rename_draft,
    },
    ConflictKind.subject_grade_mismatch: set(),
}


def allowed_actions_for_conflict(kind: ConflictKind) -> list[str]:
    allowed = _ALLOWED_ACTIONS.get(kind, set())
    return [action.value for action in sorted(allowed, key=lambda item: item.value)]


class KpIngestReviewService:
    def __init__(
        self,
        ingest_svc: Optional[TextbookIngestService] = None,
        catalog_svc: Optional[KpCatalogService] = None,
        wiki_sync_svc: Optional["KpWikiSyncService"] = None,
    ) -> None:
        self._ingest = ingest_svc or TextbookIngestService()
        self._catalog = catalog_svc or get_kp_catalog_service()
        self._wiki_sync = wiki_sync_svc

    def _draft_from_job(self, job: TextbookIngestJob) -> KpDocumentDraft:
        if not job.parsed_draft:
            raise ValueError(f"job {job.job_id} has no parsed_draft (not a kp-doc ingest)")
        return KpDocumentDraft.model_validate(job.parsed_draft)

    def build_snapshot(self, job: TextbookIngestJob) -> IngestReviewSnapshot:
        draft = self._draft_from_job(job)
        if draft.is_questions_only():
            diff = CatalogDiff(
                subject=draft.subject,
                grade=draft.grade,
                units=[],
                conflicts=[],
            )
        else:
            diff = self._catalog.diff_with_draft(draft)
        resolutions = [
            ConflictResolutionEntry.model_validate(r)
            for r in (job.conflict_resolutions or [])
        ]
        res_by_id = {r.conflict_id: r for r in resolutions}

        checklist = self._build_format_checklist(job, draft)
        blocking = self._count_unresolved(diff, res_by_id)
        ready = (
            job.status == IngestJobStatus.pending_review
            and blocking == 0
            and all(item.satisfied for item in checklist if item.required)
        )

        return IngestReviewSnapshot(
            catalog_diff=diff,
            checklist=checklist,
            conflict_resolutions=resolutions,
            confirm_subject_grade=bool(job.review_flags.get("confirm_subject_grade")),
            confirm_write=bool(job.review_flags.get("confirm_write")),
            ready_to_approve=ready,
            blocking_unresolved=blocking,
        )

    def refresh_job_review(self, job_id: str) -> TextbookIngestJob:
        job = self._ingest.get_job(job_id)
        snapshot = self.build_snapshot(job)
        job.catalog_diff = snapshot.catalog_diff.model_dump(mode="json")
        job.review_checklist = [c.model_dump(mode="json") for c in snapshot.checklist]
        job.ready_to_approve = snapshot.ready_to_approve
        self._ingest._save(job)
        return job

    def attach_review_to_job(self, job: TextbookIngestJob) -> TextbookIngestJob:
        snapshot = self.build_snapshot(job)
        job.catalog_diff = snapshot.catalog_diff.model_dump(mode="json")
        job.review_checklist = [c.model_dump(mode="json") for c in snapshot.checklist]
        job.ready_to_approve = snapshot.ready_to_approve
        return job

    def set_resolution(
        self,
        job_id: str,
        conflict_id: str,
        action: ResolutionAction,
        *,
        new_knowledge_point_id: Optional[str] = None,
        note: Optional[str] = None,
    ) -> TextbookIngestJob:
        job = self._ingest.get_job(job_id)
        if job.status != IngestJobStatus.pending_review:
            raise ValueError(f"job {job_id} is not pending_review")

        snapshot = self.build_snapshot(job)
        conflict = next((c for c in snapshot.catalog_diff.conflicts if c.conflict_id == conflict_id), None)
        if conflict is None:
            raise KeyError(f"unknown conflict_id: {conflict_id}")

        allowed = _ALLOWED_ACTIONS.get(conflict.kind, set())
        if action not in allowed:
            raise ValueError(
                f"action {action.value} not allowed for {conflict.kind.value}; "
                f"allowed: {[a.value for a in sorted(allowed, key=lambda x: x.value)]}"
            )
        if action == ResolutionAction.rename_draft and not new_knowledge_point_id:
            raise ValueError("rename_draft requires new_knowledge_point_id")

        entries = [
            ConflictResolutionEntry.model_validate(r)
            for r in (job.conflict_resolutions or [])
            if r.get("conflict_id") != conflict_id
        ]
        entries.append(
            ConflictResolutionEntry(
                conflict_id=conflict_id,
                action=action,
                new_knowledge_point_id=new_knowledge_point_id,
                note=note,
            )
        )
        job.conflict_resolutions = [e.model_dump(mode="json") for e in entries]
        self._ingest._save(job)
        return self.refresh_job_review(job_id)

    def set_review_flag(self, job_id: str, flag: str, value: bool = True) -> TextbookIngestJob:
        job = self._ingest.get_job(job_id)
        if job.status != IngestJobStatus.pending_review:
            raise ValueError(f"job {job_id} is not pending_review")
        flags = dict(job.review_flags or {})
        if flag not in {"confirm_subject_grade", "confirm_write"}:
            raise ValueError(f"unknown review flag: {flag}")
        flags[flag] = value
        job.review_flags = flags
        self._ingest._save(job)
        return self.refresh_job_review(job_id)

    def _build_format_checklist(
        self,
        job: TextbookIngestJob,
        draft: KpDocumentDraft,
    ) -> list[ReviewChecklistItem]:
        from agent_platform.learning.question_bank_ingest import validate_draft_questions

        warnings = list(draft.parse_warnings or [])
        unit_count = len(draft.units)
        kp_count = draft.knowledge_point_count
        q_count = draft.question_count
        empty_units = [
            u.unit_id for u in draft.units if not u.knowledge_points and not u.questions
        ]

        items = [
            ReviewChecklistItem(
                rule_id="F1",
                title="Markdown / YAML 解析成功",
                satisfied=True,
                detail=(
                    f"学科 {draft.subject} · {draft.grade} 年级 · "
                    f"{unit_count} 单元 · {kp_count} 知识点 · {q_count} 练习题"
                ),
            ),
            ReviewChecklistItem(
                rule_id="F2",
                title="Frontmatter 必填项",
                satisfied=bool(draft.subject and draft.grade and draft.textbook_ref),
                detail=f"教材版本：{draft.textbook_ref or '（缺失）'}",
            ),
            ReviewChecklistItem(
                rule_id="F3",
                title="单元结构（知识点和/或练习题）",
                satisfied=unit_count > 0 and not empty_units,
                detail=(
                    f"共 {unit_count} 单元"
                    if not empty_units
                    else f"以下单元为空：{', '.join(empty_units)}"
                ),
            ),
            ReviewChecklistItem(
                rule_id="F4",
                title="格式警告",
                satisfied=len(warnings) == 0,
                detail="无" if not warnings else "；".join(warnings),
            ),
        ]

        if draft.has_questions():
            qval = validate_draft_questions(draft, catalog=self._catalog)
            items.append(
                ReviewChecklistItem(
                    rule_id="Q1",
                    title="练习题字段与引用校验",
                    satisfied=qval.ok,
                    detail="；".join(qval.errors) if qval.errors else f"共 {qval.question_count} 道题",
                )
            )
            items.append(
                ReviewChecklistItem(
                    rule_id="Q2",
                    title="练习题警告",
                    required=False,
                    satisfied=len(qval.warnings) == 0,
                    detail="无" if not qval.warnings else "；".join(qval.warnings),
                )
            )
        elif not draft.has_knowledge_points():
            items.append(
                ReviewChecklistItem(
                    rule_id="F5",
                    title="文档含知识点或练习题",
                    satisfied=False,
                    detail="至少需要知识点列表或练习题之一",
                )
            )

        return items

    def _build_checklist(
        self,
        job: TextbookIngestJob,
        diff: CatalogDiff,
        resolutions: dict[str, ConflictResolutionEntry],
    ) -> list[ReviewChecklistItem]:
        """Legacy alias — format checklist only."""
        draft = KpDocumentDraft.model_validate(job.parsed_draft or {})
        return self._build_format_checklist(job, draft)

    @staticmethod
    def _count_unresolved(
        diff: CatalogDiff,
        resolutions: dict[str, ConflictResolutionEntry],
    ) -> int:
        count = 0
        for conflict in diff.conflicts:
            if conflict.kind == ConflictKind.subject_grade_mismatch:
                continue
            if conflict.conflict_id not in resolutions:
                count += 1
        return count

    def reject(self, job_id: str, reason: Optional[str] = None) -> TextbookIngestJob:
        job = self._ingest.get_job(job_id)
        if job.status != IngestJobStatus.pending_review:
            raise ValueError(f"job {job_id} is not pending_review")
        job.status = IngestJobStatus.rejected
        if reason:
            job.notes = list(job.notes) + [f"rejected: {reason}"]
        self._ingest._save(job)
        return job

    def approve(self, job_id: str) -> "CatalogApproveResult":
        from agent_platform.learning.kp_catalog_merge import (
            CatalogApproveResult,
            CatalogMergeReport,
            KpCatalogWriter,
            KpWikiSyncSummary,
            merge_approved_draft,
        )
        from agent_platform.learning.question_bank_ingest import import_draft_questions

        job = self._ingest.get_job(job_id)
        if job.status != IngestJobStatus.pending_review:
            raise ValueError(f"job {job_id} is not pending_review")
        if job.source_type.value != "kp-doc":
            raise ValueError(f"job {job_id} is not a kp-doc ingest")

        snapshot = self.build_snapshot(job)
        if not snapshot.ready_to_approve:
            raise ValueError(
                f"job {job_id} not ready_to_approve "
                f"(blocking_unresolved={snapshot.blocking_unresolved})"
            )

        draft = self._draft_from_job(job)
        resolutions = [
            ConflictResolutionEntry.model_validate(r)
            for r in (job.conflict_resolutions or [])
        ]

        catalog_merged = draft.has_knowledge_points()
        backup_path = ""
        audit_path = ""
        merge_report = CatalogMergeReport(job_id=job_id)

        if catalog_merged:
            merged, merge_report = merge_approved_draft(
                self._catalog.catalog,
                draft,
                snapshot.catalog_diff,
                resolutions,
            )
            merge_report.job_id = job_id

            writer = KpCatalogWriter(
                self._catalog,
                audit_dir=self._ingest._root / "_kp_catalog_audit",  # noqa: SLF001
            )
            backup_path = str(writer.save_with_backup(merged))
            audit_path = str(
                writer.write_audit_record(
                    job_id=job_id,
                    backup_path=Path(backup_path),
                    merge_report=merge_report,
                    source_path=job.source_path,
                )
            )
            self._catalog.reload()

        questions_imported = 0
        question_warnings: list[str] = []
        question_archive: str | None = None
        if draft.has_questions():
            q_result = import_draft_questions(
                draft,
                source_path=job.source_path,
                archive=True,
            )
            questions_imported = q_result.imported
            question_warnings = list(q_result.warnings)
            question_archive = q_result.archive_path

        job.status = IngestJobStatus.approved
        job.approved_at = utc_now().isoformat()
        if backup_path:
            job.catalog_backup_path = backup_path
        job.merge_report = merge_report.model_dump(mode="json")
        job.ready_to_approve = False
        notes = list(job.notes)
        if catalog_merged:
            notes.append("approved: merged into kp_catalog.json")
        if questions_imported:
            notes.append(f"approved: imported {questions_imported} question(s) into SQLite")
        job.notes = notes
        self._ingest._save(job)

        wiki_sync = KpWikiSyncSummary()
        if catalog_merged:
            try:
                from agent_platform.learning.kp_wiki_sync import KpWikiSyncService

                wiki_svc = self._wiki_sync or KpWikiSyncService(catalog=self._catalog)
                wiki_report = wiki_svc.sync_draft_after_approve(
                    draft,
                    merge_report,
                    job_id=job_id,
                )
                wiki_sync = KpWikiSyncSummary(
                    pages_synced=wiki_report.pages_synced,
                    page_paths=wiki_report.page_paths,
                    warnings=wiki_report.warnings,
                )
                if wiki_report.pages_synced:
                    notes.append(f"approved: synced {wiki_report.pages_synced} wiki page(s)")
                    job.notes = notes
                    self._ingest._save(job)
            except Exception as exc:  # noqa: BLE001
                wiki_sync = KpWikiSyncSummary(warnings=[f"wiki sync failed: {exc}"])

        return CatalogApproveResult(
            job_id=job_id,
            catalog_path=str(self._catalog._path),  # noqa: SLF001
            backup_path=backup_path,
            audit_path=audit_path,
            merge_report=merge_report,
            catalog_merged=catalog_merged,
            questions_imported=questions_imported,
            question_import_warnings=question_warnings,
            question_archive_path=question_archive,
            wiki_sync=wiki_sync,
        )
