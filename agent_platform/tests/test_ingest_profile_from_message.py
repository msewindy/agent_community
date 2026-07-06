"""Tests for chat message profile ingestion."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.profile_onboarding import ingest_profile_clues_from_message
from agent_platform.learning.student_context import StudentContextService
from agent_platform.memory.profile_completeness import (
    extract_grade_label_from_text,
    extract_interest_phrase_from_text,
)


def _init_student(data: Path, sid: str = "stu-intro-01") -> None:
    from agent_platform.learning.contracts import Curriculum, PipelineStage, StudentContextInit

    ctx = StudentContextService(data_root=data)
    ctx.init(
        sid,
        StudentContextInit(
            curriculum=Curriculum(
                grade="三年级",
                grade_level=3,
                subject="数学",
                unit_id="math-g3-mixed-ops",
                unit_title="混合运算（第一单元）",
            ),
            pipeline_stage=PipelineStage.onboarding,
        ),
    )
    OnboardingService(data_root=data).onboard(
        sid,
        grade="三年级",
        grade_level=3,
        primary_subject="数学",
    )


def test_extract_grade_and_interest() -> None:
    msg = "我叫盈熙，我要上3年级了，我喜欢跳舞和画画"
    assert extract_grade_label_from_text(msg) == "三年级"
    assert "跳舞" in (extract_interest_phrase_from_text(msg) or "")


def test_ingest_from_self_intro_message(tmp_path: Path) -> None:
    data = tmp_path / "student_data"
    sid = "stu-intro-01"
    _init_student(data, sid)
    msg = "我叫盈熙，我要上3年级了，我喜欢跳舞和画画"
    snap = ingest_profile_clues_from_message(sid, msg, data_root=data)
    assert snap.display_name == "盈熙"
    assert snap.has_interest
    profile = json.loads((data / sid / "onboarding_profile.json").read_text(encoding="utf-8"))
    assert profile["preferred_name"] == "盈熙"
