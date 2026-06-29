#!/usr/bin/env python3
"""P0 acceptance — G2 onboarding, attempts, parent report, safety, web panel."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from agent_platform.api.student_panel import create_app
from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.kp_catalog import GradeBoundaryError, KpCatalogService
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.parent_report import ParentReportService
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.student_safety import StudentSafetyService
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def accept_p0_smoke() -> int:
    catalog = KpCatalogService()
    try:
        catalog.assert_student_may_access_unit(1, "math-g2-add-sub-100")
        return _fail("grade 1 should not access grade 2 unit")
    except GradeBoundaryError:
        pass

    safety = StudentSafetyService()
    blocked = safety.check_user_message("帮我代写作文")
    if blocked.allowed:
        return _fail("safety should block ghostwriting")
    if not blocked.redirect_message:
        return _fail("safety missing redirect_message")

    with tempfile.TemporaryDirectory(prefix="learning-p0-") as td:
        root = Path(td) / "student_data"
        sid = "demo-stu-g2"
        onboard = OnboardingService(data_root=root)
        profile = onboard.onboard(sid, grade="二年级", grade_level=2, primary_subject="数学")
        if profile.active_unit_id != "math-g2-add-sub-100":
            return _fail(f"onboard unit={profile.active_unit_id}")

        ctx_svc = StudentContextService(data_root=root)
        ctx = ctx_svc.get(sid)
        if ctx.curriculum.unit_title != "100以内加减法":
            return _fail(f"unit_title={ctx.curriculum.unit_title}")

        att_svc = AttemptService(data_root=root, context_svc=ctx_svc)
        for _ in range(3):
            att_svc.submit(sid, "q-g2m-002", "80")
        att_svc.submit(sid, "q-g2m-002", "85")
        att_svc.submit(sid, "q-g2m-003", "83")
        att_svc.submit(sid, "q-g2m-009", "75")

        report_svc = ParentReportService(data_root=root)
        report = report_svc.build_weekly_report(sid, period_days=7)
        if report.attempts_total < 6:
            return _fail(f"attempts_total={report.attempts_total}")
        if not report.summary:
            return _fail("empty parent summary")
        saved = report_svc.save_report(report)
        if not saved.is_file():
            return _fail("parent report not saved")

        from fastapi.testclient import TestClient

        panel_ctx = StudentContextService(data_root=root)
        panel_report = ParentReportService(data_root=root)
        client = TestClient(
            create_app(report_svc=panel_report, context_svc=panel_ctx)
        )
        health = client.get("/health")
        if health.status_code != 200:
            return _fail(f"panel health: {health.status_code}")
        api = client.get(f"/api/students/{sid}/parent-report?days=7")
        if api.status_code != 200:
            return _fail(f"panel report api: {api.status_code} {api.text}")
        payload = api.json()
        if payload.get("attempts_total", 0) < 6:
            return _fail(f"panel payload: {payload}")

        repo = Path(__file__).resolve().parents[2]
        cli = repo / "agent_platform" / "learning" / "cli_student.py"
        env = {**dict(__import__("os").environ), "PYTHONPATH": str(repo)}
        pr = __import__("subprocess").run(
            [
                sys.executable,
                str(cli),
                "--data-root",
                str(root),
                "parent-report",
                sid,
                "--save",
            ],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(repo),
            check=False,
        )
        if pr.returncode != 0:
            return _fail(f"cli parent-report: {pr.stderr}")
        cli_payload = json.loads(pr.stdout)
        if "_saved_path" not in cli_payload:
            return _fail("cli parent-report missing saved path")

        ingest_svc = TextbookIngestService(data_root=root)
        samples = Path(td) / "ingest_samples"
        samples.mkdir()
        pdf = samples / "unit.pdf"
        pdf.write_bytes(b"%PDF-1.4 pilot")
        photo = samples / "page.jpg"
        photo.write_bytes(b"\xff\xd8\xff")
        doc = samples / "unit.md"
        doc.write_text("# 二年级\n", encoding="utf-8")
        ingest_svc.submit_pdf(pdf, subject="数学")
        ingest_svc.submit_photo(photo, subject="语文")
        ingest_svc.submit_document(doc, subject="语文")
        if len(ingest_svc.list_jobs(status=IngestJobStatus.pending_review)) < 3:
            return _fail("expected 3 pending_review ingest jobs")

        _ok("grade boundary blocks grade 1 → grade 2 unit")
        _ok("safety blocks off-topic + redirect")
        _ok("onboarding → G2 math unit")
        _ok("attempts + parent weekly report")
        _ok("web panel health + report API")
        _ok("cli parent-report --save")
        _ok("textbook ingest pdf/photo/document → pending_review")

    print("accept_learning_p0_smoke: PASS")
    return 0


def main() -> int:
    return accept_p0_smoke()


if __name__ == "__main__":
    raise SystemExit(main())
