"""Tests for learning_focus_set."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_platform.integrations.hermes import student_tools as st
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.learning_focus import set_learning_focus
from agent_platform.learning.student_context import StudentContextService

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def focus_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    sid = "focus-stu-1"
    monkeypatch.setenv("STUDENT_JARVIS_DATA_ROOT", str(data))
    monkeypatch.setenv("STUDENT_JARVIS_STUDENT_ID", sid)
    st._ctx_svc = None
    st._gap_svc = None
    st._push_svc = None
    StudentContextService(data_root=data).init_from_defaults(sid)
    yield sid, data, catalog


def test_set_focus_switches_to_english(focus_env) -> None:
    sid, data, _ = focus_env
    result = set_learning_focus(sid, "english-g3-u01", data_root=data)
    assert result.success is True
    assert result.unit_id == "english-g3-u01"
    assert result.subject == "英语"
    ctx = StudentContextService(data_root=data).get(sid)
    assert ctx.curriculum.unit_id == "english-g3-u01"
    assert ctx.curriculum.updated_by == "jarvis"


def test_set_focus_already_current(focus_env) -> None:
    sid, data, _ = focus_env
    set_learning_focus(sid, "english-g3-u01", data_root=data)
    again = set_learning_focus(sid, "english-g3-u01", data_root=data)
    assert again.already_current is True


def test_learning_focus_set_tool(focus_env) -> None:
    sid, _, _ = focus_env
    out = json.loads(st.learning_focus_set({"student_id": sid, "unit_id": "english-g3-u01"}))
    assert out["success"] is True
    assert out["unit_id"] == "english-g3-u01"


def test_learning_catalog_lookup_tool(focus_env) -> None:
    sid, _, _ = focus_env
    out = json.loads(
        st.learning_catalog_lookup(
            {"student_id": sid, "subject": "英语", "unit_num": 1},
        )
    )
    assert out["success"] is True
    assert out["unit"]["unit_id"] == "english-g3-u01"
