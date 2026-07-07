"""学生聊天页语音：静态契约与路由测试（Web Speech 在浏览器端，无 /api/asr）。"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.student_chat import create_app

_TEMPLATES = Path(__file__).resolve().parents[1] / "api" / "templates"


def test_student_chat_uses_browser_web_speech_not_server_asr():
    html = (_TEMPLATES / "student_chat.html").read_text(encoding="utf-8")
    assert "webkitSpeechRecognition" in html or "SpeechRecognition" in html
    assert "/api/asr" not in html
    assert "MediaRecorder" not in html


def test_speech_diag_template_exists_and_documents_no_server_asr():
    html = (_TEMPLATES / "speech_diag.html").read_text(encoding="utf-8")
    assert "Web Speech API" in html
    assert "localhost:8771" in html
    assert "onerror" in html


def test_speech_diag_route_served():
    client = TestClient(create_app())
    r = client.get("/speech-diag")
    assert r.status_code == 200
    assert "语音识别诊断" in r.text
    assert "onresult" in r.text


def test_chat_page_handles_no_speech_retry():
    html = (_TEMPLATES / "student_chat.html").read_text(encoding="utf-8")
    assert "no-speech" in html
    assert "VOICE_NO_SPEECH_MAX" in html
    assert "e.error === 'network'" in html


def test_no_asr_api_on_student_chat_backend():
    """8771 当前未暴露服务端 ASR；Network 看不到本项目 ASR 是预期行为。"""
    client = TestClient(create_app())
    for method, path in [("post", "/api/asr"), ("get", "/api/asr")]:
        resp = getattr(client, method)(path)
        assert resp.status_code == 404
