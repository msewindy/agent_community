"""Phase 1 — StudentContextService tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.contracts import (
    Curriculum,
    PipelineStage,
    StudentContextInit,
    StudentContextPatch,
)
from agent_platform.learning.student_context import StudentContextService


@pytest.fixture
def svc(tmp_path: Path) -> StudentContextService:
    return StudentContextService(data_root=tmp_path / "student_data")


@pytest.fixture
def curriculum() -> Curriculum:
    return Curriculum(
        grade="二年级",
        grade_level=2,
        subject="数学",
        unit_id="math-g2-add-sub-100",
        unit_title="100以内加减法",
    )


def test_init_writes_valid_context(svc: StudentContextService, curriculum: Curriculum) -> None:
    ctx = svc.init("s1", StudentContextInit(curriculum=curriculum))
    assert ctx.schema_version == "1.0.0"
    assert ctx.student_id == "s1"
    assert svc.exists("s1")


def test_patch_updates_stage_and_timestamp(svc: StudentContextService, curriculum: Curriculum) -> None:
    svc.init("s1", StudentContextInit(curriculum=curriculum))
    before = svc.get("s1")
    updated = svc.patch("s1", StudentContextPatch(pipeline_stage=PipelineStage.remediation))
    assert updated.pipeline_stage == PipelineStage.remediation
    assert updated.updated_at >= before.updated_at
    assert updated.trace_id != before.trace_id


def test_invalid_stage_rejected_at_patch(svc: StudentContextService, curriculum: Curriculum) -> None:
    svc.init("s1", StudentContextInit(curriculum=curriculum))
    with pytest.raises(Exception):
        StudentContextPatch.model_validate({"pipeline_stage": "not_a_stage"})


def test_to_prompt_block(svc: StudentContextService, curriculum: Curriculum) -> None:
    svc.init("s1", StudentContextInit(curriculum=curriculum, pipeline_stage=PipelineStage.learning))
    block = svc.to_prompt_block(student_id="s1")
    assert "100以内加减法" in block
    assert "新知学习" in block


def test_duplicate_init_raises(svc: StudentContextService, curriculum: Curriculum) -> None:
    svc.init("s1", StudentContextInit(curriculum=curriculum))
    with pytest.raises(FileExistsError):
        svc.init("s1", StudentContextInit(curriculum=curriculum))


def test_get_missing_raises(svc: StudentContextService) -> None:
    with pytest.raises(FileNotFoundError):
        svc.get("missing")


def test_focus_max_lengths(svc: StudentContextService, curriculum: Curriculum) -> None:
    svc.init("s1", StudentContextInit(curriculum=curriculum))
    updated = svc.merge_focus(
        "s1",
        top_gap_ids=[f"g{i}" for i in range(5)],
        queue_head_question_ids=[f"q{i}" for i in range(8)],
    )
    assert len(updated.focus.top_gap_ids) == 3
    assert len(updated.focus.queue_head_question_ids) == 5
