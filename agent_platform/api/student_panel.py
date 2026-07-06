"""P0/P1 — FastAPI parent panel + KP ingest review (Web)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field
from urllib.parse import quote

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.profile_onboarding import refresh_student_display_name
from agent_platform.learning.student_identity import resolve_student_friendly_name, student_list_label
from agent_platform.learning.bootstrap_family_alpha import ensure_family_alpha_content
from agent_platform.learning.kp_catalog import (
    KpCatalogService,
    get_kp_catalog_service,
    invalidate_kp_catalog_cache,
)
from agent_platform.learning.kp_catalog_diff import CatalogTree, ConflictKind
from agent_platform.learning.kp_ingest_review import (
    KpIngestReviewService,
    ResolutionAction,
    allowed_actions_for_conflict,
)
from agent_platform.learning.learning_dashboard import LearningDashboardOut, LearningDashboardService
from agent_platform.learning.learning_profile import LearningProfileOut, LearningProfileService
from agent_platform.learning.photo_triage import PhotoTriageService
from agent_platform.learning.kp_review_display import (
    ACTION_LABELS,
    build_document_tree,
    build_kb_comparison,
    localize_conflict,
)
from agent_platform.learning.kp_template import (
    KP_FORMAT_GUIDE_BRIEF,
    KP_MD_TEMPLATE,
    KP_QUESTIONS_ONLY_TEMPLATE,
    QUESTIONS_FORMAT_GUIDE_BRIEF,
)
from agent_platform.learning.parent_report import ParentReportService
from agent_platform.learning.question_bank_ingest import question_bank_overview
from agent_platform.learning.question_inbox import QuestionInboxService
from agent_platform.learning.question_pending_review import is_question_bank_queue
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestService
from agent_platform.learning.unit_switch import UnitSwitchService
from agent_platform.learning.kp_catalog_export import KpCatalogExportService

_TEMPLATES = Path(__file__).parent / "templates"
_PANEL_SHELL = (_TEMPLATES / "panel_shell.html").read_text(encoding="utf-8")
_PANEL_CSS = (_TEMPLATES / "panel_shell.css").read_text(encoding="utf-8")
_PANEL_HTML = (_TEMPLATES / "student_overview.html").read_text(encoding="utf-8")
_LEARNING_DETAIL_HTML = (_TEMPLATES / "learning_detail.html").read_text(encoding="utf-8")
_EXERCISE_HUB_HTML = (_TEMPLATES / "exercise_hub.html").read_text(encoding="utf-8")
_WEEKLY_REPORT_HTML = (_TEMPLATES / "weekly_report.html").read_text(encoding="utf-8")
_KP_REVIEW_HTML = (_TEMPLATES / "kp_review.html").read_text(encoding="utf-8")
_KP_CATALOG_HTML = (_TEMPLATES / "kp_catalog.html").read_text(encoding="utf-8")
_QUESTION_BANK_HTML = (_TEMPLATES / "question_bank.html").read_text(encoding="utf-8")

_NAV = (
    ("/", "overview", "学情总览", "📊"),
    ("/learning-detail", "detail", "学情详情", "📖"),
    ("/weekly-report", "report", "学习周报", "📋"),
    ("/kp-catalog", "catalog", "浏览知识库", "📚"),
    ("/exercises", "exercises", "习题处理", "📝"),
    ("/kp-review", "review", "知识点入库", "📥"),
)


def _render_sidebar(active: str) -> str:
    parts = []
    for href, key, label, icon in _NAV:
        cls = "nav-item active" if key == active else "nav-item"
        parts.append(f'<a href="{href}" class="{cls}"><span class="nav-icon">{icon}</span>{label}</a>')
    return "\n".join(parts)


def _panel_page(
    content: str,
    *,
    title: str,
    active: str,
    body_class_page: str = "",
    extra_head: str = "",
) -> str:
    return (
        _PANEL_SHELL.replace("{{INLINE_CSS}}", _PANEL_CSS)
        .replace("{{SIDEBAR}}", _render_sidebar(active))
        .replace("{{PAGE_TITLE}}", title)
        .replace("{{CONTENT}}", content)
        .replace("{{BODY_CLASS}}", "")
        .replace("{{BODY_CLASS_PAGE}}", body_class_page)
        .replace("{{EXTRA_HEAD}}", extra_head)
        .replace("{{EXTRA_SCRIPT}}", "")
    )


def _attachment_disposition(filename: str) -> str:
    ascii_name = re.sub(r"[^A-Za-z0-9._-]", "_", filename) or "kp-export.kp.md"
    return f"attachment; filename=\"{ascii_name}\"; filename*=UTF-8''{quote(filename)}"


def _live_catalog() -> KpCatalogService:
    """Always read catalog from disk (mtime-based singleton reload)."""
    return get_kp_catalog_service()


class StudentSummaryOut(BaseModel):
    student_id: str
    display_name: str
    display_label: str
    grade: str = ""
    has_nickname: bool = False


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
    volume: Optional[dict] = None
    evaluation: Optional[dict] = None
    recommendations: list[dict] = Field(default_factory=list)


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
    sample_id: str = Field(pattern="^(math-g2|chinese-g2|math-g3)$")


class TriageResolveIn(BaseModel):
    knowledge_point_id: str = Field(min_length=1)
    is_correct: bool
    error_code: Optional[str] = None


class TriageDropIn(BaseModel):
    note: Optional[str] = None


class PendingQuestionPatchIn(BaseModel):
    expected_answer: Optional[str] = None
    knowledge_point_id: Optional[str] = None
    explanation: Optional[str] = None


class PendingQuestionImportIn(BaseModel):
    question_ids: Optional[list[str]] = None


class LearningUnitSwitchIn(BaseModel):
    unit_id: str = Field(min_length=1)


_KP_SAMPLES: dict[str, Path] = {
    "math-g2": repo_root() / "docs" / "content" / "数学-二年级.kp.md",
    "chinese-g2": repo_root() / "docs" / "content" / "语文-二年级.kp.md",
    "math-g3": repo_root() / "docs" / "content" / "数学-三年级.kp.md",
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
    catalog = catalog_svc or get_kp_catalog_service()
    ingest = ingest_svc or TextbookIngestService(data_root=data_root)
    review = review_svc or KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)
    question_inbox_svc = QuestionInboxService(data_root=data_root)
    profile_svc = LearningProfileService(
        data_root=data_root,
        catalog=catalog,
        question_inbox_svc=question_inbox_svc,
    )
    triage_svc = PhotoTriageService(data_root=data_root, catalog=catalog)
    unit_switch_svc = UnitSwitchService(data_root=data_root, catalog_svc=catalog)
    dashboard_svc = LearningDashboardService(
        data_root=data_root,
        context_svc=ctx_svc,
        catalog=catalog,
        config=cfg,
    )
    kp_export_svc = KpCatalogExportService(catalog=catalog)
    bootstrap_report = ensure_family_alpha_content()

    app = FastAPI(title="Student Jarvis Panel", version="0.4.0-family-alpha-p0")

    def _html_vars(html: str) -> str:
        return html.replace("{{DATA_ROOT}}", root_label)

    def _render_page(fragment: str, *, title: str, active: str, body_class_page: str = "") -> str:
        return _html_vars(_panel_page(fragment, title=title, active=active, body_class_page=body_class_page))

    @app.get("/health")
    def health() -> dict[str, str | int | dict]:
        return {
            "status": "ok",
            "grade_pilot": int((cfg.get("pilot") or {}).get("grade_level", 2)),
            "port": int(panel_cfg.get("port", 8770)),
            "bootstrap": bootstrap_report.to_dict(),
        }

    @app.get("/", response_class=HTMLResponse)
    def panel_page() -> str:
        return _render_page(_PANEL_HTML, title="学情总览", active="overview")

    @app.get("/learning-detail", response_class=HTMLResponse)
    def learning_detail_page() -> str:
        return _render_page(_LEARNING_DETAIL_HTML, title="学情详情", active="detail")

    @app.get("/exercises", response_class=HTMLResponse)
    def exercises_page() -> str:
        return _render_page(_EXERCISE_HUB_HTML, title="习题处理", active="exercises")

    @app.get("/weekly-report", response_class=HTMLResponse)
    def weekly_report_page() -> str:
        return _render_page(_WEEKLY_REPORT_HTML, title="学习周报", active="report")

    @app.get("/kp-review", response_class=HTMLResponse)
    def kp_review_page() -> str:
        return _render_page(_KP_REVIEW_HTML, title="知识点入库", active="review", body_class_page="page-body-flush")

    @app.get("/kp-catalog", response_class=HTMLResponse)
    def kp_catalog_page() -> str:
        return _render_page(_KP_CATALOG_HTML, title="浏览知识库", active="catalog")

    @app.get("/question-bank", response_class=HTMLResponse)
    def question_bank_page() -> str:
        return _render_page(_EXERCISE_HUB_HTML, title="习题处理", active="exercises")

    @app.get("/api/question-bank/info")
    def question_bank_info() -> JSONResponse:
        return JSONResponse(question_bank_overview())

    @app.get("/api/question-bank/format-template")
    def question_bank_format_template() -> Response:
        return Response(
            content=KP_QUESTIONS_ONLY_TEMPLATE.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=kp-questions-only.kp.md",
            },
        )

    @app.post("/api/question-bank/upload")
    async def question_bank_upload(file: UploadFile = File(...)) -> JSONResponse:
        """Upload questions-only `.kp.md` → 习题处理待归类队列。"""
        if not file.filename:
            raise HTTPException(status_code=400, detail="missing filename")
        content = await file.read()
        try:
            text = content.decode("utf-8")
        except UnicodeDecodeError as e:
            raise HTTPException(status_code=400, detail="file must be UTF-8 text") from e

        from agent_platform.learning.kp_document_parser import KpDocumentParseError, parse_kp_document_text

        try:
            draft = parse_kp_document_text(text, source_path=file.filename)
        except KpDocumentParseError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        if not draft.has_questions():
            raise HTTPException(status_code=400, detail="document has no ## 练习题 section")
        if draft.has_knowledge_points():
            raise HTTPException(
                status_code=400,
                detail="此入口仅接受「仅练习题」文档；含知识点请用「知识点入库」",
            )

        added = question_inbox_svc.upsert_from_draft(draft, source_ref=file.filename)
        return JSONResponse(
            {
                "success": True,
                "added": len(added),
                "redirect_review": "/exercises",
                "hint": f"已加入待归类 {len(added)} 道题，请补全答案后导入题库",
            }
        )

    @app.get("/api/question-bank/format-guide", response_class=PlainTextResponse)
    def question_bank_format_guide() -> str:
        return QUESTIONS_FORMAT_GUIDE_BRIEF

    @app.get("/api/question-bank/inbox")
    def list_question_inbox() -> JSONResponse:
        items = question_inbox_svc.list_pending()
        return JSONResponse(
            {"count": len(items), "items": [e.model_dump(mode="json") for e in items]}
        )

    @app.patch("/api/question-bank/inbox/{entry_id}")
    def patch_question_inbox(entry_id: str, body: PendingQuestionPatchIn) -> JSONResponse:
        try:
            entry = question_inbox_svc.update_entry(
                entry_id,
                expected_answer=body.expected_answer,
                knowledge_point_id=body.knowledge_point_id,
                explanation=body.explanation,
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(entry.model_dump(mode="json"))

    @app.post("/api/question-bank/inbox/{entry_id}/import")
    def import_question_inbox(entry_id: str, body: PendingQuestionPatchIn) -> JSONResponse:
        try:
            result = question_inbox_svc.import_entry(
                entry_id,
                expected_answer=body.expected_answer,
                knowledge_point_id=body.knowledge_point_id,
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(result)

    @app.post("/api/question-bank/inbox/import-ready")
    def import_all_question_inbox() -> JSONResponse:
        return JSONResponse(question_inbox_svc.import_all_ready())

    @app.post("/api/question-bank/inbox/{entry_id}/drop")
    def drop_question_inbox(entry_id: str) -> JSONResponse:
        try:
            entry = question_inbox_svc.drop_entry(entry_id)
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return JSONResponse(entry.model_dump(mode="json"))

    @app.get("/api/kp/format-template")
    def kp_format_template() -> Response:
        """Download blank `.kp.md` template for parents."""
        return Response(
            content=KP_MD_TEMPLATE.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers={
                "Content-Disposition": "attachment; filename=kp-template.kp.md",
            },
        )

    @app.get("/api/kp/format-guide", response_class=PlainTextResponse)
    def kp_format_guide() -> str:
        return KP_FORMAT_GUIDE_BRIEF

    @app.post("/api/kp/catalog/reload")
    def catalog_reload() -> JSONResponse:
        """Reload kp_catalog.json from disk into this panel process."""
        invalidate_kp_catalog_cache()
        svc = _live_catalog()
        cat = svc.catalog
        kp_count = sum(len(u.knowledge_points) for u in cat.units)
        return JSONResponse(
            {
                "success": True,
                "unit_count": len(cat.units),
                "knowledge_point_count": kp_count,
                "hint": "家长端浏览知识库已刷新；孩子端 8771 会在下次提问时自动加载新 catalog。",
            }
        )

    @app.get("/api/kp/catalog/info", response_model=CatalogInfoOut)
    def catalog_info() -> CatalogInfoOut:
        svc = _live_catalog()
        cat = svc.catalog
        kp_count = sum(len(u.knowledge_points) for u in cat.units)
        try:
            rel_path = str(svc._path.relative_to(repo_root())).replace("\\", "/")  # noqa: SLF001
        except ValueError:
            rel_path = str(svc._path)
        subjects = sorted({u.subject for u in cat.units})
        return CatalogInfoOut(
            catalog_path=rel_path,
            schema_version=cat.schema_version,
            school_stage=cat.school_stage,
            unit_count=len(cat.units),
            knowledge_point_count=kp_count,
            subjects=subjects,
        )

    @app.get("/api/kp/catalog/export")
    def export_kp_catalog(
        subject: str = Query(..., min_length=1),
        grade: int = Query(..., ge=1, le=6),
        unit_id: Optional[str] = Query(None),
        include_questions: bool = Query(True),
    ) -> Response:
        """Export catalog slice to downloadable `.kp.md` for offline edit."""
        try:
            result = kp_export_svc.export(
                subject=subject,
                grade=grade,
                unit_id=unit_id,
                include_questions=include_questions,
            )
        except KeyError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        headers = {
            "Content-Disposition": _attachment_disposition(result.filename),
            "X-Export-Units": ",".join(result.unit_ids),
            "X-Export-Kp-Count": str(result.knowledge_point_count),
            "X-Export-Question-Count": str(result.question_count),
        }
        return Response(
            content=result.content.encode("utf-8"),
            media_type="text/markdown; charset=utf-8",
            headers=headers,
        )

    @app.get("/api/students", response_model=list[StudentSummaryOut])
    def list_students() -> list[StudentSummaryOut]:
        if not data_root.is_dir():
            return []
        out: list[StudentSummaryOut] = []
        for p in sorted(data_root.iterdir()):
            if not p.is_dir() or not (p / "context.json").is_file():
                continue
            sid = p.name
            try:
                ctx = ctx_svc.get(sid)
                refresh_student_display_name(sid, cfg=cfg, data_root=data_root)
                friendly = resolve_student_friendly_name(
                    sid, cfg, ctx=ctx, data_root=data_root
                )
                grade = ctx.curriculum.grade or ""
                out.append(
                    StudentSummaryOut(
                        student_id=sid,
                        display_name=friendly or "未设置昵称",
                        display_label=student_list_label(
                            sid, cfg, grade=grade, ctx=ctx, data_root=data_root
                        ),
                        grade=grade,
                        has_nickname=bool(friendly),
                    )
                )
            except FileNotFoundError:
                continue
        return out

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
        tree = _live_catalog().list_tree()
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
        status: Optional[IngestJobStatus] = Query(IngestJobStatus.pending_review),
        include_questions: bool = Query(
            False,
            description="为 true 时包含「仅练习题」待审批次（应在习题处理待归类）",
        ),
        include_rejected: bool = Query(False, description="为 true 时包含已拒绝记录"),
    ) -> list[IngestJobSummary]:
        if include_rejected and status == IngestJobStatus.pending_review:
            jobs = ingest.list_jobs(status=None)
            jobs = [j for j in jobs if j.status in (IngestJobStatus.pending_review, IngestJobStatus.rejected)]
        else:
            jobs = ingest.list_jobs(status=status)
        if not include_questions:
            jobs = [j for j in jobs if not is_question_bank_queue(j)]
        return [_job_summary(job) for job in jobs]

    @app.get("/api/kp/ingest/samples")
    def list_kp_samples() -> JSONResponse:
        items = []
        _sample_meta = {
            "math-g2": ("数学", 2),
            "chinese-g2": ("语文", 2),
            "math-g3": ("数学", 3),
        }
        for sample_id, path in _KP_SAMPLES.items():
            subject, grade = _sample_meta.get(sample_id, ("", 0))
            items.append(
                {
                    "sample_id": sample_id,
                    "filename": path.name,
                    "available": path.is_file(),
                    "subject": subject,
                    "grade": grade,
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
        doc_tree = build_document_tree(draft)
        question_count = sum(len(u.get("questions") or []) for u in doc_tree)

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
                "document_content": doc_tree,
                "question_count": question_count,
                "questions_only": bool(draft.get("units")) and not any(
                    (u.get("knowledge_points") or []) for u in draft.get("units") or []
                ) and question_count > 0,
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
        payload = result.model_dump(mode="json")
        parts: list[str] = []
        if result.catalog_merged:
            parts.append("知识点已写入知识库，下次孩子提问时 Jarvis 会自动加载（无需重启 8771）。")
        if result.questions_imported:
            parts.append(f"已导入 {result.questions_imported} 道练习题到题库。")
        if result.wiki_sync.pages_synced:
            parts.append(f"已同步 {result.wiki_sync.pages_synced} 个知识点的 Wiki 讲解页。")
        if not parts:
            parts.append("入库完成。")
        if result.catalog_merged and not result.questions_imported:
            parts.append("若新单元要练题，可在同一 .kp.md 中补充 ## 练习题 后再次上传。")
        elif result.questions_imported and not result.catalog_merged:
            parts.append("请到学情页「当前学习单元」切换到新单元，让孩子练新题。")
        elif result.questions_imported:
            parts.append("请到学情页「当前学习单元」切换到新单元后练题。")
        payload["post_approve_hint"] = "".join(parts)
        return JSONResponse(payload)

    @app.post("/api/kp/ingest/jobs/{job_id}/reject")
    def reject_job(job_id: str, body: RejectIn) -> JSONResponse:
        _get_kp_doc_job(job_id)
        try:
            job = review.reject(job_id, reason=body.reason)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(job.model_dump(mode="json"))

    @app.get("/api/students/{student_id}/learning-unit")
    def get_learning_unit(student_id: str) -> JSONResponse:
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        try:
            snap = unit_switch_svc.get_snapshot(student_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        return JSONResponse(snap.to_dict())

    @app.post("/api/students/{student_id}/learning-unit")
    def switch_learning_unit(student_id: str, body: LearningUnitSwitchIn) -> JSONResponse:
        from agent_platform.learning.kp_catalog import GradeBoundaryError

        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        try:
            result = unit_switch_svc.switch_active_unit(student_id, body.unit_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e
        except GradeBoundaryError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e)) from e
        return JSONResponse(result.to_dict())

    @app.get("/api/students/{student_id}/learning-dashboard", response_model=LearningDashboardOut)
    def get_learning_dashboard(student_id: str) -> LearningDashboardOut:
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        try:
            return dashboard_svc.build(student_id)
        except FileNotFoundError as e:
            raise HTTPException(status_code=404, detail=str(e)) from e

    @app.get("/api/students/{student_id}/learning-profile", response_model=LearningProfileOut)
    def get_learning_profile(
        student_id: str,
        unit_id: Optional[str] = None,
        subject: Optional[str] = Query(None),
        grade: Optional[int] = Query(None, ge=1, le=6),
        gap_limit: int = Query(50, ge=0, le=200),
        include_pending: bool = Query(True),
    ) -> LearningProfileOut:
        """学情详情：可按单元过滤；待归类题在习题处理页操作。"""
        if not ctx_svc.exists(student_id):
            raise HTTPException(status_code=404, detail=f"student not found: {student_id}")
        return profile_svc.get_profile(
            student_id,
            gap_limit=gap_limit,
            unit_id=unit_id,
            subject=subject,
            grade=grade,
            include_pending=include_pending,
        )

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
