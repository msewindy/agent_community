"""P1-1 — student panel question bank routes."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_platform.api.student_panel import create_app
from agent_platform.learning.textbook_ingest import TextbookIngestService


def test_question_bank_page_and_info(tmp_path: Path) -> None:
    cfg = {
        "data": {"root": str(tmp_path / "student_data")},
        "web_panel": {"port": 8770},
        "pilot": {"grade_level": 3},
    }
    app = create_app(config=cfg)
    client = TestClient(app)

    page = client.get("/question-bank")
    assert page.status_code == 200
    assert "待归类" in page.text
    assert "studentSelect" not in page.text

    info = client.get("/api/question-bank/info")
    assert info.status_code == 200
    body = info.json()
    assert "total_questions" in body
    assert "units" in body

    tpl = client.get("/api/question-bank/format-template")
    assert tpl.status_code == 200
    assert "## 练习题" in tpl.text


def test_question_bank_upload_questions_only(tmp_path: Path) -> None:
    data_root = tmp_path / "student_data"
    cfg = {
        "data": {"root": str(data_root)},
        "web_panel": {"port": 8770},
        "pilot": {"grade_level": 3},
    }
    ingest = TextbookIngestService(data_root=data_root)
    app = create_app(config=cfg, ingest_svc=ingest)
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
