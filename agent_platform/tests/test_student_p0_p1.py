"""P0/P1 — teach preflight, grade boundary, scene behavior, ASR route."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.student_chat import create_app
from agent_platform.learning.grade_boundary import check_grade_boundary_message
from agent_platform.learning.scene_behavior import student_behavior_prompt_block
from agent_platform.learning.teach_preflight import parse_teach_target, run_teach_preflight
from agent_platform.learning.student_reply import sanitize_student_reply

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def focus_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    from agent_platform.learning.kp_catalog import KpCatalogService
    from agent_platform.learning.student_context import StudentContextService

    sid = "p0-stu-1"
    monkeypatch.setenv("STUDENT_JARVIS_DATA_ROOT", str(data))
    monkeypatch.setenv("STUDENT_JARVIS_STUDENT_ID", sid)
    monkeypatch.setenv("KP_CATALOG_PATH", str(catalog_path))
    StudentContextService(data_root=data).init_from_defaults(sid)
    yield sid, data, KpCatalogService(catalog_path=catalog_path)


def test_parse_teach_target_chinese_u1() -> None:
    subj, num = parse_teach_target("我想学小学语文第一单元")
    assert subj == "语文"
    assert num == 1


def test_teach_preflight_aligns_chinese_u1(focus_env) -> None:
    sid, data, _ = focus_env
    block = run_teach_preflight(sid, "贾维斯，我想学习一下小学语文第一单元")
    assert "讲新课预检" in block
    assert "chinese-g3-u01" in block or "语文" in block
    assert "勿向" in block


def test_grade_boundary_high_school() -> None:
    block = check_grade_boundary_message("讲讲高中物理", student_grade_level=3)
    assert block is not None
    assert "超纲" in block or "还没学到" in block


def test_scene_behavior_block() -> None:
    block = student_behavior_prompt_block()
    assert "三年级学伴" in block
    assert "共情" in block


def test_sanitize_strips_tool_names() -> None:
    raw = "根据 `learning_focus_set` 已对齐。\n\n好的，我们来学《美丽的校园》。"
    clean = sanitize_student_reply(raw)
    assert "learning_focus_set" not in clean
    assert "美丽的校园" in clean


def test_welcome_includes_learning_context(focus_env) -> None:
    sid, _, _ = focus_env
    client = TestClient(create_app())
    r = client.get("/api/chat/welcome", params={"student_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body.get("grade_label")
    assert body.get("learning_context_line")


def test_asr_route_requires_audio() -> None:
    client = TestClient(create_app())
    r = client.post("/api/asr", files={"audio": ("empty.webm", b"", "audio/webm")})
    assert r.status_code in (400, 502)
