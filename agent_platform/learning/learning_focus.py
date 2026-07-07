"""Jarvis-side learning focus (unit switch with catalog validation)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agent_platform.learning.kp_catalog import KpCatalogService, get_kp_catalog_service
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.unit_switch import UnitSwitchService


@dataclass
class LearningFocusResult:
    success: bool
    student_id: str
    unit_id: str
    unit_title: str = ""
    subject: str = ""
    textbook_ref: Optional[str] = None
    knowledge_points: list[dict[str, str]] = field(default_factory=list)
    already_current: bool = False
    push_queue_size: int = 0
    push_head_question_ids: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    reason: str = ""

    def to_dict(self) -> dict:
        hint = (
            "单元未变；勿向学生提及已对齐/不用切换，直接讲解。"
            if self.already_current
            else "切换后讲新课请先 explain_kp；练题用 questions_suggest。"
        )
        return {
            "success": self.success,
            "student_id": self.student_id,
            "unit_id": self.unit_id,
            "unit_title": self.unit_title,
            "subject": self.subject,
            "textbook_ref": self.textbook_ref,
            "knowledge_points": self.knowledge_points,
            "already_current": self.already_current,
            "push_queue": {
                "item_count": self.push_queue_size,
                "head_question_ids": self.push_head_question_ids,
            },
            "warnings": self.warnings,
            "reason": self.reason,
            "hint": hint,
        }


class LearningFocusService:
    def __init__(
        self,
        *,
        data_root: Optional[Path] = None,
        context_svc: Optional[StudentContextService] = None,
        catalog_svc: Optional[KpCatalogService] = None,
        unit_switch_svc: Optional[UnitSwitchService] = None,
    ) -> None:
        self._ctx = context_svc or StudentContextService(data_root=data_root)
        self._catalog = catalog_svc or get_kp_catalog_service()
        self._switch = unit_switch_svc or UnitSwitchService(
            data_root=data_root,
            context_svc=self._ctx,
            catalog_svc=self._catalog,
        )

    def set_focus(
        self,
        student_id: str,
        unit_id: str,
        *,
        reason: str = "",
    ) -> LearningFocusResult:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        unit_id = unit_id.strip()
        unit = self._catalog.get_unit(unit_id)
        ctx = self._ctx.get(student_id)
        kps = [
            {"knowledge_point_id": kp.knowledge_point_id, "title": kp.title}
            for kp in unit.knowledge_points
        ]

        if ctx.curriculum.unit_id == unit_id:
            queue_size = 0
            head_ids: list[str] = []
            try:
                items = self._switch._push.peek(student_id, limit=100)  # noqa: SLF001
                queue_size = len(items)
                head_ids = [i.question_id for i in items[:5]]
            except FileNotFoundError:
                pass
            return LearningFocusResult(
                success=True,
                student_id=student_id,
                unit_id=unit.unit_id,
                unit_title=unit.unit_title,
                subject=unit.subject,
                textbook_ref=unit.textbook_ref,
                knowledge_points=kps,
                already_current=True,
                push_queue_size=queue_size,
                push_head_question_ids=head_ids,
                reason=reason,
            )

        switch = self._switch.switch_active_unit(student_id, unit_id, updated_by="jarvis")
        return LearningFocusResult(
            success=switch.success,
            student_id=student_id,
            unit_id=switch.new_unit_id,
            unit_title=switch.new_unit_title,
            subject=unit.subject,
            textbook_ref=unit.textbook_ref,
            knowledge_points=kps,
            already_current=False,
            push_queue_size=switch.push_queue_size,
            push_head_question_ids=switch.push_head_question_ids,
            warnings=switch.warnings,
            reason=reason,
        )


def set_learning_focus(
    student_id: str,
    unit_id: str,
    *,
    reason: str = "",
    data_root: Optional[Path] = None,
) -> LearningFocusResult:
    return LearningFocusService(data_root=data_root).set_focus(
        student_id,
        unit_id,
        reason=reason,
    )
