"""Tests for question inbox (exercises 待归类)."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_platform.api.student_panel import create_app
from agent_platform.learning.kp_document_parser import KpDocumentDraft, KpDocumentQuestion, KpDocumentUnit
from agent_platform.learning.question_inbox import QuestionInboxService


def _sample_draft() -> KpDocumentDraft:
    return KpDocumentDraft(
        subject="英语",
        grade=3,
        textbook_ref="测试版",
        units=[
            KpDocumentUnit(
                unit_id="english-g3-u01",
                unit_title="A new start",
                questions=[
                    KpDocumentQuestion(
                        question_id="q-en3-u01-pending-001",
                        stem="【待人工补全】Listen",
                        knowledge_point_id="kp-en-g3-u01-reading",
                        expected_answer="TBD",
                        explanation="待审",
                        default_error_code="EN_READING_ERROR",
                    ),
                ],
            )
        ],
    )


def test_question_inbox_and_profile(tmp_path: Path) -> None:
    data_root = tmp_path / "student_data"
    cfg = {"data": {"root": str(data_root)}, "web_panel": {"port": 8770}, "pilot": {"grade_level": 3}}
    inbox = QuestionInboxService(data_root=data_root)
    inbox.upsert_from_draft(_sample_draft(), source_ref="test")

    app = create_app(config=cfg)
    client = TestClient(app)

    listed = client.get("/api/question-bank/inbox")
    assert listed.status_code == 200
    assert listed.json()["count"] == 1

    kp_jobs = client.get("/api/kp/ingest/jobs")
    assert kp_jobs.status_code == 200
    assert kp_jobs.json() == []


def test_question_bank_upload_goes_to_inbox(tmp_path: Path) -> None:
    data_root = tmp_path / "student_data"
    cfg = {"data": {"root": str(data_root)}, "web_panel": {"port": 8770}, "pilot": {"grade_level": 3}}
    app = create_app(config=cfg)
    client = TestClient(app)
    tpl = client.get("/api/question-bank/format-template").text
    res = client.post(
        "/api/question-bank/upload",
        files={"file": ("only-q.kp.md", tpl.encode("utf-8"), "text/markdown")},
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["success"] is True
    assert body["added"] >= 1
    assert client.get("/api/kp/ingest/jobs").json() == []
