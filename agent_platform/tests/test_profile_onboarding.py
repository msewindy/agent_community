"""Tests for L1 profile onboarding welcome + stage helpers."""

from __future__ import annotations

import json
from pathlib import Path

from agent_platform.learning.contracts import PipelineStage
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.profile_onboarding import (
    build_welcome_message,
    maybe_advance_from_onboarding,
    snapshot_for_student,
)
from agent_platform.learning.student_context import StudentContextService
from agent_platform.memory.contracts import MemoryCategory, MemoryKind, MemoryRecord
from agent_platform.memory.profile_completeness import ProfileSnapshot


def test_welcome_message_variants() -> None:
    assert "初次见面" in build_welcome_message(ProfileSnapshot(missing=["name", "grade", "interest"]))
    assert "画画" not in build_welcome_message(
        ProfileSnapshot(has_display_name=True, display_name="小明", missing=["interest"])
    ) or "喜欢" in build_welcome_message(
        ProfileSnapshot(has_display_name=True, display_name="小明", missing=["interest"])
    )
    assert "小明" in build_welcome_message(
        ProfileSnapshot(
            has_display_name=True,
            has_grade_hint=True,
            has_interest=True,
            display_name="小明",
            missing=[],
        )
    )


def test_maybe_advance_from_onboarding(tmp_path: Path) -> None:
    data = tmp_path / "student_data"
    ctx = StudentContextService(data_root=data)
    catalog = __import__(
        "agent_platform.learning.kp_catalog", fromlist=["KpCatalogService"]
    ).KpCatalogService()
    onboarding = OnboardingService(data_root=data, context_svc=ctx, catalog=catalog)
    sid = "g2-stu-01"
    ctx.init_from_defaults(sid)
    onboarding.onboard(sid, grade="三年级", grade_level=3, primary_subject="数学")
    ctx.patch(sid, __import__("agent_platform.learning.contracts", fromlist=["StudentContextPatch"]).StudentContextPatch(
        pipeline_stage=PipelineStage.onboarding
    ))

    class _Mem:
        default_device_id = "reachy-desktop-01"

        def list_records(self, **kwargs):
            return [
                MemoryRecord(
                    record_id="1",
                    device_id="reachy-desktop-01",
                    ts="2026-01-01T00:00:00Z",
                    category=MemoryCategory.user_profile,
                    kind=MemoryKind.fact,
                    content="孩子叫测试生，三年级。",
                    content_hash="x",
                ),
                MemoryRecord(
                    record_id="2",
                    device_id="reachy-desktop-01",
                    ts="2026-01-01T00:00:00Z",
                    category=MemoryCategory.preference,
                    kind=MemoryKind.fact,
                    content="喜欢踢足球",
                    content_hash="y",
                ),
            ]

    assert maybe_advance_from_onboarding(sid, data_root=data, memory_svc=_Mem()) is True
    assert ctx.get(sid).pipeline_stage == PipelineStage.learning
    prof = json.loads((data / sid / "onboarding_profile.json").read_text(encoding="utf-8"))
    assert prof.get("preferred_name") == "测试生"
