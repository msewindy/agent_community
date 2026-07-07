"""Refresh nickname from M2 into onboarding profile."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.profile_onboarding import refresh_student_display_name
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.student_identity import resolve_student_friendly_name
from agent_platform.memory.contracts import MemoryCategory, MemoryKind, MemoryRecord, MemorySearchResult


def _init_student(data: Path, sid: str = "g2-stu-01") -> None:
    from agent_platform.learning.contracts import Curriculum, PipelineStage, StudentContextInit

    ctx = StudentContextService(data_root=data)
    ctx.init(
        sid,
        StudentContextInit(
            curriculum=Curriculum(
                grade="三年级",
                grade_level=3,
                subject="数学",
                unit_id="math-g3-u01",
                unit_title="两步四则运算（第一单元）",
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


def test_refresh_persists_name_to_onboarding_profile(tmp_path: Path) -> None:
    data = tmp_path / "student_data"
    sid = "g2-stu-01"
    _init_student(data, sid)

    mem = MagicMock()
    mem.default_device_id = "dev-1"
    mem.list_records.return_value = [
        MemoryRecord(
            record_id="r1",
            device_id="dev-1",
            category=MemoryCategory.user_profile,
            kind=MemoryKind.fact,
            content="孩子叫小明，三年级，喜欢足球。",
            content_hash="x",
            trace_id="t",
        )
    ]
    mem.search.return_value = MemorySearchResult(hits=[])

    name = refresh_student_display_name(sid, data_root=data, memory_svc=mem)
    assert name == "小明"

    profile = json.loads((data / sid / "onboarding_profile.json").read_text(encoding="utf-8"))
    assert profile["preferred_name"] == "小明"
    assert (
        resolve_student_friendly_name(
            sid,
            {"students": {"profiles": {sid: {"memory_device_id": "dev-1"}}}},
            memory_svc=mem,
            data_root=data,
        )
        == "小明"
    )
