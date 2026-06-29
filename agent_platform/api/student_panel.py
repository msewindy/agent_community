"""P0/P1 — FastAPI parent panel + KP ingest review (Web)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, Field

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_catalog_diff import CatalogTree, ConflictKind
from agent_platform.learning.kp_ingest_review import (
    KpIngestReviewService,
    ResolutionAction,
    allowed_actions_for_conflict,
)
from agent_platform.learning.learning_profile import LearningProfileOut, LearningProfileService
from agent_platform.learning.photo_triage import PhotoTriageService
from agent_platform.learning.kp_review_display import (
    ACTION_LABELS,
    build_document_tree,
    build_kb_comparison,
    localize_conflict,
)
from agent_platform.learning.parent_report import ParentReportService
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestService

_TEMPLATES = Path(__file__).parent / "templates"
_PANEL_HTML = (_TEMPLATES / "student_panel.html").read_text(encoding="utf-8")
_KP_REVIEW_HTML = (_TEMPLATES / "kp_review.html").read_text(encoding="utf-8")
_KP_CATALOG_HTML = (_TEMPLATES / "kp_catalog.html").read_text(encoding="utf-8")


class CatalogInfoOut(BaseModel):
    catalog_path: str
    schema_version: str
    school_stage: str
    unit_count: int
    knowledge_point_count: int
    subjects: list[str] = Field(default_factory=list)


class ParentReportOut(BaseModel):
    student_id: str
    period_days: int
    generated_at: str
    grade: str
    subject: str
    unit_title: str
    summary: str
    knowledge_highlights: list[str]
    behavior_notes: list[str]
    next_steps: list[str]
    attempts_total: int
    correct_rate: Optional[float] = None
    dimension_scores: list[dict] = Field(default_factory=list)
    evidence: list[dict] = Field(default_factory=list)


class IngestJobSummary(BaseModel):
    job_id: str
    status: str
    status_label: str
    source_path: str
    source_filename: str
    source_type: str
    ready_to_approve: bool = False
    subject: Optional[str] = None
    grade: Optional[int] = None
    created_at: str
    approved_at: Optional[str] = None


class ConflictResolveIn(BaseModel):
    conflict_id: str
    action: ResolutionAction
    new_knowledge_point_id: Optional[str] = None
    note: Optional[str] = None


class ReviewConfirmIn(BaseModel):
    flag: str = Field(pattern="^(confirm_subject_grade|confirm_write)$")
    value: bool = True


class RejectIn(BaseModel):
    reason: Optional[str] = None


class SubmitSampleIn(BaseModel):
    sample_id: str = Field(pattern="^(math-g2|chinese-g2)$")


class TriageResolveIn(BaseModel):
    knowledge_point_id: str = Field(min_length=1)
    is_correct: bool
    error_code: Optional[str] = None


class TriageDropIn(BaseModel):
    note: Optional[str] = None


_KP_SAMPLES: dict[str, Path] = {
    "math-g2": repo_root() / "docs" / "content" / "数学-二年级.kp.md",
    "chinese-g2": repo_root() / "docs" / "content" / "语文-二年级.kp.md",
}


_KP_STATUS_LABELS = {
    "pending_review": "审核中",
    "approved": "已通过",
    "rejected": "已拒绝",
}


def _job_summary(job) -> IngestJobSummary:
    draft = job.parsed_draft or {}
    display_name = job.client_filename or Path(job.source_path).name
    return IngestJobSummary(
        job_id=job.job_id,
        status=job.status.value,
        status_label=_KP_STATUS_LABELS.get(job.status.value, job.status.value),
        source_path=job.source_path,
        source_filename=display_name,
        source_type=job.source_type.value,
        ready_to_approve=job.ready_to_approve,
        subject=draft.get("subject"),
        grade=draft.get("grade"),
        created_at=job.created_at,
        approved_at=getattr(job, "approved_at", None),
    )


def _upload_original_filename(source_path: str) -> str:
    """Strip ``YYYYMMDD-HHMMSS-`` prefix from Web upload storage names."""
    name = Path(source_path).name
    match = re.match(r"^\d{8}-\d{6}-(.+)$", name)
    return match.group(1) if match else name


def _display_source(job) -> dict[str, Optional[str]]:
    if getattr(job, "client_source_path", None):
        return {
            "display_path": job.client_source_path,
            "storage_path": job.source_path,
            "hint": None,
        }
    name = getattr(job, "client_filename", None) or _upload_original_filename(job.source_path)
    repo_candidate = repo_root() / "docs" / "content" / name
    if repo_candidate.is_file():
        return {
            "display_path": f"docs/content/{name}",
            "storage_path": job.source_path,
            "hint": None,
        }
    return {
        "display_path": name,
        "storage_path": job.source_path,
        "hint": "浏览器上传无法读取本地完整路径，可在「新建提交」中填写来源路径。",
    }


def _resolve_data_root(cfg: dict) -> Path:
    raw = (cfg.get("data") or {}).get("root", "student_data")
    path = Path(raw)
    if not path.is_absolute():
        path = repo_root() / path
    return path.resolve()


def create_app(
    config: Optional[dict] = None,
    report_svc: Optional[ParentReportService] = None,
    context_svc: Optional[StudentContextService] = None,
    catalog_svc: Optional[KpCatalogService] = None,
    ingest_svc: Optional[TextbookIngestService] = None,
    review_svc: Optional[KpIngestReviewService] = None,
) -> FastAPI:
    cfg = config or load_student_learning_config()
    panel_cfg = cfg.get("web_panel") or {}
    data_root = _resolve_data_root(cfg)
    root_label = str((cfg.get("data") or {}).get("root", "student_data"))

    report = report_svc or ParentReportService(data_root=data_root)
    ctx_svc = context_svc or StudentContextService(data_root=data_root)
    catalog = catalog_svc or KpCatalogService()
    ingest = ingest_svc or TextbookIngestService(data_root=data_root)
    review = review_svc or KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)
    profile_svc = LearningProfileService(data_root=data_root, catalog=catalog)
    triage_svc = PhotoTriageService(data_root=data_root, catalog=catalog)

    app = FastAPI(title="Student Jarvis Panel", version="0.3.0-p1-web-e2e")

    def _html_vars(html: str) -> str:
        return html.replace("{{DATA_ROOT}}", root_label)

    @app.get("/health")
    def health() -> dict[str, str | int]:
        return {
            "status": "ok",
            "grade_pilot": int((cfg.get("pilot") or {}).get("grade_level", 2)),
            "port": int(panel_cfg.get("port", 8770)),
        }

    @app.get("/", response_class=HTMLResponse)
    def panel_page() -> str:
        return _html_vars(_PANEL_HTML)

    @app.get("/kp-review", response_class=HTMLResponse)
    def kp_review_page() -> str:
        return _html_vars(_KP_REVIEW_HTML)

    @app.get("/kp-catalog", response_class=HTMLResponse)
    def kp_catalog_page() -> str:
        return _html_vars(_KP_CATALOG_HTML)

    @app.get("/api/kp/catalog/info", response_model=CatalogInfoOut)
    def catalog_info() -> CatalogInfoOut:
        cat = catalog.catalog
        kp_count = sum(len(u.knowledge_points) for u in cat.units)
        try:
            rel_path = str(catalog._path.relative_to(repo_root())).replace("\\", "/")  # noqa: SLF001
        except ValueError:
            rel_path = str(catalog._path)
        subjects = sorted({u.subject for u in cat.units})
        return CatalogInfoOut(
            catalog_path=rel_path,
            schema_version=cat.schema_version,
            school_stage=cat.school_stage,
            unit_count=len(cat.units),
            knowledge_point_count=kp_count,
            subjects=subjects,
        )

    @app.get("/api/students", response_model=list[str])
    def list_students() -> list[str]:
        if not data_root.is_dir():
            return []
        return sorted(
            p.name for p in data_root.iterdir() if p.is_dir() and (p / "context.json").is_file()
        )

    @app.get("/api/students/{student_id}/parent-report", response_model=ParentReportOut)
    def get_parent_report(
        student_id: str,
        days: int = Query(7, ge=1, le=90),
        save: bool = Query(False),
    ) -> ParentReportOut:
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        try:
            weekly = report.build_weekly_report(student_id, period_days=days)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        if save:
            report.save_report(weekly)
        payload = weekly.model_dump(mode="json")
        return ParentReportOut.model_validate(payload)

    @app.post("/api/students/{student_id}/parent-report/generate")
    def generate_parent_report(student_id: str, days: int = Query(7, ge=1, le=90)) -> JSONResponse:
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        weekly = report.build_weekly_report(student_id, period_days=days)
        path = report.save_report(weekly)
        return JSONResponse(
            {
                "success": True,
                "saved_path": str(path),
                "report": weekly.model_dump(mode="json"),
            }
        )

    @app.get("/api/kp/catalog/tree", response_model=CatalogTree)
    def catalog_tree(
        subject: Optional[str] = None,
        grade: Optional[int] = Query(None, ge=1, le=6),
    ) -> CatalogTree:
        tree = catalog.list_tree()
        if subject is None and grade is None:
            return tree
        subjects = []
        for subj in tree.subjects:
            if subject is not None and subj.subject != subject:
                continue
            grades = []
            for grade_node in subj.grades:
                if grade is not None and grade_node.grade != grade:
                    continue
                grades.append(grade_node)
            if grades:
                subjects.append(subj.model_copy(update={"grades": grades}))
        return CatalogTree(subjects=subjects)

    @app.get("/api/kp/ingest/jobs", response_model=list[IngestJobSummary])
    def list_ingest_jobs(
        status: Optional[IngestJobStatus] = Query(None),
    ) -> list[IngestJobSummary]:
        jobs = ingest.list_jobs(status=status)
        return [_job_summary(job) for job in jobs]

    @app.get("/api/kp/ingest/samples")
    def list_kp_samples() -> JSONResponse:
        items = []
        for sample_id, path in _KP_SAMPLES.items():
            items.append(
                {
                    "sample_id": sample_id,
                    "filename": path.name,
                    "available": path.is_file(),
                    "subject": "数学" if sample_id == "math-g2" else "语文",
                    "grade": 2,
                }
            )
        return JSONResponse({"samples": items})

    @app.post("/api/kp/ingest/submit")
    async def submit_kp_upload(
        file: UploadFile = File(...),
        client_source_path: Optional[str] = Form(None),
    ) -> JSONResponse:
        filename = Path(file.filename or "").name
        if not filename:
            raise HTTPException(status_code=400, detail="缺少文件名")
        if not (filename.endswith(".kp.md") or filename.endswith(".md")):
            raise HTTPException(status_code=400, detail="仅支持 .kp.md / .md 文件")

        upload_dir = data_root / "_kp_uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        from agent_platform.learning.contracts import utc_now

        ts = utc_now().strftime("%Y%m%d-%H%M%S")
        dest = upload_dir / f"{ts}-{filename}"
        content = await file.read()
        if not content.strip():
            raise HTTPException(status_code=400, detail="文件为空")
        dest.write_bytes(content)

        try:
            job = ingest.submit_kp_document(dest)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            dest.unlink(missing_ok=True)
            raise HTTPException(status_code=400, detail=str(e)) from e

        job.client_filename = filename
        if client_source_path and client_source_path.strip():
            job.client_source_path = client_source_path.strip()
        else:
            repo_match = repo_root() / "docs" / "content" / filename
            if repo_match.is_file():
                job.client_source_path = f"docs/content/{filename}"
        ingest._save(job)  # noqa: SLF001

        snapshot = review.build_snapshot(job)
        return JSONResponse(
            {
                "job": _job_summary(job).model_dump(mode="json"),
                "blocking_unresolved": snapshot.blocking_unresolved,
                "conflict_count": len(snapshot.catalog_diff.conflicts),
            }
        )

    @app.post("/api/kp/ingest/submit-sample")
    def submit_kp_sample(body: SubmitSampleIn) -> JSONResponse:
        path = _KP_SAMPLES.get(body.sample_id)
        if path is None or not path.is_file():
            raise HTTPException(status_code=404, detail=f"sample not found: {body.sample_id}")
        try:
            job = ingest.submit_kp_document(path)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        job.client_filename = path.name
        try:
            job.client_source_path = str(path.relative_to(repo_root())).replace("\\", "/")
        except ValueError:
            job.client_source_path = str(path)
        ingest._save(job)  # noqa: SLF001
        snapshot = review.build_snapshot(job)
        return JSONResponse(
            {
                "job": _job_summary(job).model_dump(mode="json"),
                "blocking_unresolved": snapshot.blocking_unresolved,
                "conflict_count": len(snapshot.catalog_diff.conflicts),
            }
        )

    def _get_kp_doc_job(job_id: str):
        try:
            job = ingest.get_job(job_id)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        if job.source_type.value != "kp-doc":
            raise HTTPException(status_code=400, detail=f"job {job_id} is not kp-doc")
        return job

    @app.get("/api/kp/ingest/jobs/{job_id}")
    def get_ingest_job(job_id: str) -> JSONResponse:
        job = _get_kp_doc_job(job_id)
        return JSONResponse(job.model_dump(mode="json"))

    @app.get("/api/kp/ingest/jobs/{job_id}/review")
    def get_ingest_review(job_id: str) -> JSONResponse:
        job = _get_kp_doc_job(job_id)
        try:
            if job.status == IngestJobStatus.pending_review:
                job = review.refresh_job_review(job_id)
            snapshot = review.build_snapshot(job)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e

        draft = job.parsed_draft or {}
        resolution_by_id = {item.conflict_id: item for item in snapshot.conflict_resolutions}
        conflicts = []
        for conflict in snapshot.catalog_diff.conflicts:
            payload = conflict.model_dump(mode="json")
            payload["allowed_actions"] = allowed_actions_for_conflict(conflict.kind)
            resolved = resolution_by_id.get(conflict.conflict_id)
            res_dict = resolved.model_dump(mode="json") if resolved else None
            payload["resolution"] = res_dict
            payload["blocking"] = conflict.kind != ConflictKind.subject_grade_mismatch
            conflicts.append(localize_conflict(payload, res_dict))

        source = _display_source(job)
        kb_comparison = build_kb_comparison(snapshot.catalog_diff, snapshot.conflict_resolutions)

        return JSONResponse(
            {
                "job_id": job.job_id,
                "status": job.status.value,
                "status_label": _KP_STATUS_LABELS.get(job.status.value, job.status.value),
                "source_path": job.source_path,
                "source_filename": job.client_filename or Path(job.source_path).name,
                "display_path": source["display_path"],
                "display_hint": source["hint"],
                "ready_to_approve": snapshot.ready_to_approve,
                "blocking_unresolved": snapshot.blocking_unresolved,
                "format_validation": [item.model_dump(mode="json") for item in snapshot.checklist],
                "parse_warnings": draft.get("parse_warnings") or [],
                "document_preview": job.extracted_text_preview,
                "document_content": build_document_tree(draft),
                "kb_comparison": kb_comparison,
                "conflicts": conflicts,
                "catalog_diff": snapshot.catalog_diff.model_dump(mode="json"),
                "approved_at": job.approved_at,
                "catalog_backup_path": job.catalog_backup_path,
                "merge_report": job.merge_report,
                "notes": job.notes,
            }
        )

    @app.post("/api/kp/ingest/jobs/{job_id}/resolve")
    def resolve_conflict(job_id: str, body: ConflictResolveIn) -> JSONResponse:
        _get_kp_doc_job(job_id)
        try:
            job = review.set_resolution(
                job_id,
                body.conflict_id,
                body.action,
                new_knowledge_point_id=body.new_knowledge_point_id,
                note=body.note,
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(job.model_dump(mode="json"))

    @app.post("/api/kp/ingest/jobs/{job_id}/review-confirm")
    def review_confirm(job_id: str, body: ReviewConfirmIn) -> JSONResponse:
        _get_kp_doc_job(job_id)
        try:
            job = review.set_review_flag(job_id, body.flag, value=body.value)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        snapshot = review.build_snapshot(job)
        return JSONResponse(
            {
                "job_id": job.job_id,
                "flag": body.flag,
                "value": job.review_flags.get(body.flag),
                "ready_to_approve": snapshot.ready_to_approve,
            }
        )

    @app.post("/api/kp/ingest/jobs/{job_id}/approve")
    def approve_job(job_id: str) -> JSONResponse:
        _get_kp_doc_job(job_id)
        try:
            result = review.approve(job_id)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(result.model_dump(mode="json"))

    @app.post("/api/kp/ingest/jobs/{job_id}/reject")
    def reject_job(job_id: str, body: RejectIn) -> JSONResponse:
        _get_kp_doc_job(job_id)
        try:
            job = review.reject(job_id, reason=body.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(job.model_dump(mode="json"))

    @app.get("/api/students/{student_id}/learning-profile", response_model=LearningProfileOut)
    def get_learning_profile(student_id: str) -> LearningProfileOut:
        """学情总览：知识点掌握档 + 尚未归类的题（同一视图，非独立收件箱页）。"""
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        return profile_svc.get_profile(student_id)

    @app.post("/api/students/{student_id}/learning-profile/pending/{entry_id}/resolve")
    def resolve_pending_item(
        student_id: str,
        entry_id: str,
        body: TriageResolveIn,
    ) -> JSONResponse:
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        try:
            result = triage_svc.inbox_resolve(
                student_id,
                entry_id,
                knowledge_point_id=body.knowledge_point_id,
                is_correct=body.is_correct,
                error_code=body.error_code,
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(
            {
                "success": True,
                "attempt_id": result.attempt_id,
                "source": "photo_manual",
            }
        )

    @app.post("/api/students/{student_id}/learning-profile/pending/{entry_id}/drop")
    def drop_pending_item(
        student_id: str,
        entry_id: str,
        body: TriageDropIn,
    ) -> JSONResponse:
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        try:
            entry = triage_svc.inbox_drop(student_id, entry_id)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return JSONResponse(
            {
                "success": True,
                "entry_id": entry.entry_id,
                "status": entry.status,
                "note": body.note,
            }
        )

    return app


app = create_app()


def main() -> None:
    import uvicorn

    cfg = load_student_learning_config()
    panel_cfg = cfg.get("web_panel") or {}
    host = str(panel_cfg.get("host", "127.0.0.1"))
    port = int(panel_cfg.get("port", 8770))
    uvicorn.run("agent_platform.api.student_panel:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    main()
