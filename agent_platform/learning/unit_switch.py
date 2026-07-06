"""Switch student active learning unit (P1-2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_platform.learning.contracts import (
    Curriculum,
    PipelineStage,
    StudentContextPatch,
    utc_now,
)
from agent_platform.learning.kp_catalog import KpCatalogService, get_kp_catalog_service
from agent_platform.learning.onboarding import OnboardingService
from agent_platform.learning.push_engine import PushEngineService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.student_context import StudentContextService


@dataclass
class UnitChoice:
    unit_id: str
    unit_title: str
    subject: str
    grade: int
    knowledge_point_count: int
    question_count: int
    is_current: bool = False

    def to_dict(self) -> dict:
        return {
            "unit_id": self.unit_id,
            "unit_title": self.unit_title,
            "subject": self.subject,
            "grade": self.grade,
            "knowledge_point_count": self.knowledge_point_count,
            "question_count": self.question_count,
            "is_current": self.is_current,
        }


@dataclass
class LearningUnitSnapshot:
    student_id: str
    student_grade_level: int
    current: UnitChoice
    choices: list[UnitChoice]
    pipeline_stage: str
    queue_size: int = 0

    def to_dict(self) -> dict:
        return {
            "student_id": self.student_id,
            "student_grade_level": self.student_grade_level,
            "current": self.current.to_dict(),
            "choices": [c.to_dict() for c in self.choices],
            "pipeline_stage": self.pipeline_stage,
            "queue_size": self.queue_size,
        }


@dataclass
class UnitSwitchResult:
    success: bool
    student_id: str
    previous_unit_id: str
    new_unit_id: str
    new_unit_title: str
    pipeline_stage: str
    push_queue_size: int
    push_head_question_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "success": self.success,
            "student_id": self.student_id,
            "previous_unit_id": self.previous_unit_id,
            "new_unit_id": self.new_unit_id,
            "new_unit_title": self.new_unit_title,
            "pipeline_stage": self.pipeline_stage,
            "push_queue": {
                "item_count": self.push_queue_size,
                "head_question_ids": self.push_head_question_ids,
            },
            "warnings": self.warnings,
            "hint": "让孩子说「来几道题」验证是否推到新单元题目。",
        }


class UnitSwitchService:
    """Update curriculum unit + rebuild push queue from parent panel."""

    def __init__(
        self,
        data_root: Optional[Path] = None,
        context_svc: Optional[StudentContextService] = None,
        catalog_svc: Optional[KpCatalogService] = None,
        bank_svc: Optional[QuestionBankService] = None,
        push_svc: Optional[PushEngineService] = None,
        onboarding_svc: Optional[OnboardingService] = None,
    ) -> None:
        self._ctx = context_svc or StudentContextService(data_root=data_root)
        self._catalog = catalog_svc or get_kp_catalog_service()
        self._bank = bank_svc or QuestionBankService()
        self._push = push_svc or PushEngineService(data_root=data_root)
        self._onboarding = onboarding_svc or OnboardingService(
            data_root=data_root,
            context_svc=self._ctx,
            catalog=self._catalog,
        )

    def _student_grade_level(self, student_id: str) -> int:
        ctx = self._ctx.get(student_id)
        if ctx.curriculum.grade_level is not None:
            return int(ctx.curriculum.grade_level)
        try:
            profile = self._onboarding.load_profile(student_id)
            return profile.grade_level
        except FileNotFoundError:
            return self._catalog.resolve_grade_level(ctx.curriculum.grade)

    def _question_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        for q in self._bank.list_questions():
            counts[q.unit_id] = counts.get(q.unit_id, 0) + 1
        return counts

    def _choice_for_unit(
        self,
        unit,
        *,
        q_counts: dict[str, int],
        current_unit_id: str,
    ) -> UnitChoice:
        return UnitChoice(
            unit_id=unit.unit_id,
            unit_title=unit.unit_title,
            subject=unit.subject,
            grade=unit.grade,
            knowledge_point_count=len(unit.knowledge_points),
            question_count=q_counts.get(unit.unit_id, 0),
            is_current=unit.unit_id == current_unit_id,
        )

    def get_snapshot(self, student_id: str) -> LearningUnitSnapshot:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        ctx = self._ctx.get(student_id)
        grade_level = self._student_grade_level(student_id)
        q_counts = self._question_counts()
        current_unit = self._catalog.get_unit(ctx.curriculum.unit_id)
        current = self._choice_for_unit(
            current_unit,
            q_counts=q_counts,
            current_unit_id=ctx.curriculum.unit_id,
        )

        units = self._catalog.list_units(grade_level=grade_level)
        units = sorted(units, key=lambda u: (u.subject, u.grade, u.unit_id))
        choices = [
            self._choice_for_unit(u, q_counts=q_counts, current_unit_id=ctx.curriculum.unit_id)
            for u in units
        ]

        queue_size = 0
        try:
            queue_size = len(self._push.peek(student_id, limit=100))
        except FileNotFoundError:
            queue_size = 0

        return LearningUnitSnapshot(
            student_id=student_id,
            student_grade_level=grade_level,
            current=current,
            choices=choices,
            pipeline_stage=ctx.pipeline_stage.value,
            queue_size=queue_size,
        )

    def switch_active_unit(self, student_id: str, unit_id: str) -> UnitSwitchResult:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        ctx = self._ctx.get(student_id)
        previous_unit_id = ctx.curriculum.unit_id
        if unit_id == previous_unit_id:
            raise ValueError(f"student already on unit {unit_id!r}")

        grade_level = self._student_grade_level(student_id)
        self._catalog.assert_student_may_access_unit(grade_level, unit_id)

        allowed = {u.unit_id for u in self._catalog.list_units(grade_level=grade_level)}
        if unit_id not in allowed:
            raise ValueError(
                f"unit {unit_id!r} not in catalog choices for grade level {grade_level}"
            )

        unit = self._catalog.get_unit(unit_id)
        q_count = len(self._bank.list_questions(unit_id=unit_id))
        warnings: list[str] = []
        if q_count == 0:
            warnings.append(
                f"单元 {unit.unit_title}（{unit_id}）尚无练习题，孩子可能无法推题；请先到「题库管理」录入。"
            )

        new_curriculum = Curriculum(
            grade=ctx.curriculum.grade,
            subject=unit.subject,
            unit_id=unit.unit_id,
            unit_title=unit.unit_title,
            textbook_ref=unit.textbook_ref or ctx.curriculum.textbook_ref,
            grade_level=grade_level,
            updated_by="parent",
        )

        self._ctx.patch(
            student_id,
            StudentContextPatch(
                curriculum=new_curriculum,
                pipeline_stage=PipelineStage.learning,
            ),
        )

        try:
            self._onboarding.sync_active_unit(student_id, unit.unit_id, subject=unit.subject)
        except FileNotFoundError:
            pass

        queue = self._push.rebuild(student_id, sync_focus=True)
        head_ids = [item.question_id for item in queue.items[:5]]

        if q_count > 0 and len(queue.items) == 0:
            warnings.append("推题队列重建后为空，请检查 gap 与题库匹配。")
        elif q_count > 0 and len(queue.items) < queue.batch_size_min:
            warnings.append(
                f"推题队列仅 {len(queue.items)} 道（少于建议 {queue.batch_size_min} 道）。"
            )

        return UnitSwitchResult(
            success=True,
            student_id=student_id,
            previous_unit_id=previous_unit_id,
            new_unit_id=unit.unit_id,
            new_unit_title=unit.unit_title,
            pipeline_stage=PipelineStage.learning.value,
            push_queue_size=len(queue.items),
            push_head_question_ids=head_ids,
            warnings=warnings,
        )
