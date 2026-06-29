"""Textbook ingest pipeline stub — PDF / photo / document (P0).

Real parsing (OCR, PDF extract) is deferred to P1; this module records jobs
and emits review-ready KP candidates for the pilot grade.
"""

from __future__ import annotations

import json
import secrets
from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import BaseModel, Field

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.contracts import utc_now


class IngestSourceType(str, Enum):
    pdf = "pdf"
    photo = "photo"
    document = "document"
    kp_doc = "kp-doc"


class IngestJobStatus(str, Enum):
    stub_received = "stub_received"
    pending_review = "pending_review"
    approved = "approved"
    rejected = "rejected"


class KpCandidate(BaseModel):
    knowledge_point_id: str
    title: str
    confidence: float = Field(ge=0.0, le=1.0, default=0.5)
    source_span: Optional[str] = None


class TextbookIngestJob(BaseModel):
    job_id: str
    source_type: IngestSourceType
    source_path: str
    client_filename: Optional[str] = None
    client_source_path: Optional[str] = None
    status: IngestJobStatus
    grade_level: int = Field(ge=1, le=6, default=2)
    subject: Optional[str] = None
    unit_id_hint: Optional[str] = None
    extracted_text_preview: Optional[str] = None
    kp_candidates: list[KpCandidate] = Field(default_factory=list)
    parsed_draft: Optional[dict] = None
    catalog_diff: Optional[dict] = None
    review_checklist: list[dict] = Field(default_factory=list)
    conflict_resolutions: list[dict] = Field(default_factory=list)
    review_flags: dict = Field(default_factory=dict)
    ready_to_approve: bool = False
    approved_at: Optional[str] = None
    catalog_backup_path: Optional[str] = None
    merge_report: Optional[dict] = None
    notes: list[str] = Field(default_factory=list)
    created_at: str


def _new_job_id(now=None) -> str:
    ts = (now or utc_now()).strftime("%Y%m%d-%H%M%S")
    return f"ing-{ts}-{secrets.token_hex(3)}"


def _stub_preview(source_type: IngestSourceType, path: Path, subject: Optional[str]) -> str:
    subj = subject or "（未指定学科）"
    name = path.name
    if source_type == IngestSourceType.pdf:
        return (
            f"[P0 stub] PDF 已登记：{name}。"
            f"待 P1 使用 PDF 解析器提取正文（试点学科：{subj}）。"
        )
    if source_type == IngestSourceType.photo:
        return (
            f"[P0 stub] 照片已登记：{name}。"
            f"待 P1 OCR 识别课本/练习页（试点学科：{subj}）。"
        )
    return (
        f"[P0 stub] 文档已登记：{name}。"
        f"待 P1 解析 Word/Markdown 等结构化内容（试点学科：{subj}）。"
    )


def _default_kp_candidates(subject: Optional[str], grade_level: int) -> list[KpCandidate]:
    cfg = load_student_learning_config()
    pilot = cfg.get("pilot") or {}
    units = pilot.get("units") or {}
    unit_id = units.get("math") if subject == "数学" else units.get("chinese")
    if subject == "语文":
        return [
            KpCandidate(
                knowledge_point_id="kp-g2-punct-period",
                title="句号与陈述句",
                confidence=0.4,
                source_span="stub: 待审核对齐 catalog",
            ),
            KpCandidate(
                knowledge_point_id="kp-g2-word-order",
                title="语序与句子通顺",
                confidence=0.35,
                source_span="stub: 待审核对齐 catalog",
            ),
        ]
    return [
        KpCandidate(
            knowledge_point_id="kp-g2-add-carry",
            title="进位加法",
            confidence=0.45,
            source_span="stub: 待审核对齐 catalog",
        ),
        KpCandidate(
            knowledge_point_id="kp-g2-sub-borrow",
            title="退位减法",
            confidence=0.4,
            source_span="stub: 待审核对齐 catalog",
        ),
    ]


class TextbookIngestService:
    """Register ingest jobs under `{data_root}/_textbook_ingest/`."""

    def __init__(self, data_root: Optional[Path] = None) -> None:
        cfg = load_student_learning_config()
        if data_root is None:
            raw = (cfg.get("data") or {}).get("root", "student_data")
            data_root = repo_root() / raw
        self._root = Path(data_root).resolve()
        self._jobs_dir = self._root / "_textbook_ingest"

    @property
    def jobs_dir(self) -> Path:
        return self._jobs_dir

    def _job_path(self, job_id: str) -> Path:
        return self._jobs_dir / f"{job_id}.json"

    def _save(self, job: TextbookIngestJob) -> Path:
        self._jobs_dir.mkdir(parents=True, exist_ok=True)
        path = self._job_path(job.job_id)
        path.write_text(
            json.dumps(job.model_dump(mode="json"), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return path

    def submit(
        self,
        source_type: IngestSourceType,
        source_path: str | Path,
        *,
        grade_level: int = 2,
        subject: Optional[str] = None,
        unit_id_hint: Optional[str] = None,
    ) -> TextbookIngestJob:
        path = Path(source_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"ingest source not found: {path}")

        cfg = load_student_learning_config()
        pilot = cfg.get("pilot") or {}
        if unit_id_hint is None and subject:
            units = pilot.get("units") or {}
            if subject == "数学":
                unit_id_hint = units.get("math")
            elif subject == "语文":
                unit_id_hint = units.get("chinese")

        now = utc_now()
        job = TextbookIngestJob(
            job_id=_new_job_id(now),
            source_type=source_type,
            source_path=str(path),
            status=IngestJobStatus.pending_review,
            grade_level=grade_level,
            subject=subject,
            unit_id_hint=unit_id_hint,
            extracted_text_preview=_stub_preview(source_type, path, subject)[:500],
            kp_candidates=_default_kp_candidates(subject, grade_level),
            notes=[
                "P0 stub: 未执行真实 PDF/OCR/文档解析",
                "审核通过前不会写入 kp_catalog 或 question_bank",
            ],
            created_at=now.isoformat(),
        )
        self._save(job)
        return job

    def submit_pdf(self, source_path: str | Path, **kwargs) -> TextbookIngestJob:
        return self.submit(IngestSourceType.pdf, source_path, **kwargs)

    def submit_photo(self, source_path: str | Path, **kwargs) -> TextbookIngestJob:
        return self.submit(IngestSourceType.photo, source_path, **kwargs)

    def submit_document(self, source_path: str | Path, **kwargs) -> TextbookIngestJob:
        return self.submit(IngestSourceType.document, source_path, **kwargs)

    def submit_kp_document(self, source_path: str | Path) -> TextbookIngestJob:
        from agent_platform.learning.kp_document_parser import KpDocumentParseError, parse_kp_document

        path = Path(source_path).resolve()
        if not path.is_file():
            raise FileNotFoundError(f"ingest source not found: {path}")

        try:
            draft = parse_kp_document(path)
        except KpDocumentParseError as e:
            raise ValueError(str(e)) from e

        kp_candidates: list[KpCandidate] = []
        for unit in draft.units:
            for kp in unit.knowledge_points:
                kp_candidates.append(
                    KpCandidate(
                        knowledge_point_id=kp.knowledge_point_id,
                        title=kp.title,
                        confidence=1.0,
                        source_span=kp.description or unit.unit_id,
                    )
                )

        now = utc_now()
        notes = [
            "P1-A: parsed from .kp.md knowledge document",
            "审核通过前不会写入 kp_catalog 或 question_bank",
        ]
        notes.extend(draft.parse_warnings)

        job = TextbookIngestJob(
            job_id=_new_job_id(now),
            source_type=IngestSourceType.kp_doc,
            source_path=str(path),
            status=IngestJobStatus.pending_review,
            grade_level=draft.grade,
            subject=draft.subject,
            unit_id_hint=draft.units[0].unit_id if draft.units else None,
            extracted_text_preview=draft.summary_preview(),
            kp_candidates=kp_candidates,
            parsed_draft=draft.model_dump(mode="json"),
            notes=notes,
            created_at=now.isoformat(),
        )
        from agent_platform.learning.kp_ingest_review import KpIngestReviewService

        review = KpIngestReviewService(ingest_svc=self)
        job = review.attach_review_to_job(job)
        self._save(job)
        return job

    def get_job(self, job_id: str) -> TextbookIngestJob:
        path = self._job_path(job_id)
        if not path.is_file():
            raise KeyError(f"ingest job not found: {job_id}")
        raw = json.loads(path.read_text(encoding="utf-8"))
        return TextbookIngestJob.model_validate(raw)

    def list_jobs(self, status: Optional[IngestJobStatus] = None) -> list[TextbookIngestJob]:
        if not self._jobs_dir.is_dir():
            return []
        jobs: list[TextbookIngestJob] = []
        for path in sorted(self._jobs_dir.glob("ing-*.json")):
            raw = json.loads(path.read_text(encoding="utf-8"))
            job = TextbookIngestJob.model_validate(raw)
            if status is None or job.status == status:
                jobs.append(job)
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)
