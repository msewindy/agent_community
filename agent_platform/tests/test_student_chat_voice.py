"""Tests for student chat voice + server ASR."""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from agent_platform.api.student_chat import create_app

_TEMPLATES = Path(__file__).resolve().parents[1] / "api" / "templates"


def test_student_chat_prefers_server_asr_with_fallback():
    html = (_TEMPLATES / "student_chat.html").read_text(encoding="utf-8")
    assert "/api/asr" in html
    assert "MediaRecorder" in html
    assert "webkitSpeechRecognition" in html or "SpeechRecognition" in html


def test_speech_diag_template_exists_and_documents_no_server_asr():
    html = (_TEMPLATES / "speech_diag.html").read_text(encoding="utf-8")
    assert "Web Speech API" in html
    assert "localhost:8771" in html


def test_speech_diag_route_served():
    client = TestClient(create_app())
    r = client.get("/speech-diag")
    assert r.status_code == 200
    assert "语音识别诊断" in r.text


def test_asr_api_exists():
    client = TestClient(create_app())
    r = client.post("/api/asr", files={"audio": ("empty.webm", b"x", "audio/webm")})
    assert r.status_code in (400, 502)


def test_health_reports_asr_capabilities():
    client = TestClient(create_app())
    r = client.get("/health")
    assert r.status_code == 200
    assert "asr" in r.json()
