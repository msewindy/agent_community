"""Learning-domain proactive messages (Phase 6)."""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    AttemptRecord,
    GapMap,
    GapStatus,
    LearningProactiveEventType,
    LearningProactiveMessage,
    utc_now,
)
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.store import (
    append_proactive_message,
    layout_for,
    list_proactive_messages,
)
from agent_platform.learning.student_context import StudentContextService
from agent_platform.learning.taxonomy import TaxonomyService, gap_id_for_kp


def _event_id() -> str:
    return f"lp-{uuid.uuid4().hex[:12]}"


class LearningProactiveService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        ctx_svc: Optional[StudentContextService] = None,
        gap_svc: Optional[GapMapService] = None,
    ) -> None:
        self._cfg = load_student_learning_config()
        self._data_root = data_root
        self._ctx = ctx_svc or StudentContextService(data_root=data_root, config=self._cfg)
        self._gaps = gap_svc or GapMapService(data_root=data_root)
        self._taxonomy = TaxonomyService(self._cfg)

    def _is_suppressed(self, student_id: str) -> bool:
        if not self._ctx.exists(student_id):
            return False
        ctx = self._ctx.get(student_id)
        return bool(ctx.flags.do_not_disturb)

    def _emit(
        self,
        student_id: str,
        *,
        event_type: LearningProactiveEventType,
        message: str,
        gap_id: Optional[str] = None,
        attempt_id: Optional[str] = None,
    ) -> LearningProactiveMessage:
        suppressed = self._is_suppressed(student_id)
        record = LearningProactiveMessage(
            event_id=_event_id(),
            event_type=event_type,
            student_id=student_id,
            created_at=utc_now(),
            message=message,
            gap_id=gap_id,
            attempt_id=attempt_id,
            delivered=not suppressed,
            suppressed=suppressed,
        )
        append_proactive_message(
            layout_for(student_id, self._data_root).proactive_log_path,
            record,
        )
        return record

    def on_attempt(
        self,
        student_id: str,
        attempt: AttemptRecord,
        gap_map: Optional[GapMap] = None,
    ) -> list[LearningProactiveMessage]:
        if not self._cfg.get("enabled", True):
            return []
        proactive_cfg = self._cfg.get("proactive") or {}
        messages: list[LearningProactiveMessage] = []

        if proactive_cfg.get("attempt_summary_enabled", True):
            gap_id_for_summary: Optional[str] = None
            if attempt.correct:
                summary = (
                    f"练后小结：本次答对（attempt_id={attempt.attempt_id}）。"
                    f"解析：{attempt.explanation}"
                )
            else:
                # 知识点为主轴：练后小结关联的 gap 也按知识点派生
                if attempt.knowledge_point_id:
                    gap_id_for_summary = gap_id_for_kp(attempt.knowledge_point_id)
                gap_part = f" 关联 gap_id={gap_id_for_summary}。" if gap_id_for_summary else ""
                summary = (
                    f"练后小结：本次未通过（attempt_id={attempt.attempt_id}）。"
                    f"错因码 {attempt.error_code or '未知'}。{gap_part}"
                    f"解析：{attempt.explanation}"
                )
            messages.append(
                self._emit(
                    student_id,
                    event_type=LearningProactiveEventType.attempt_summary,
                    message=summary,
                    gap_id=gap_id_for_summary,
                    attempt_id=attempt.attempt_id,
                )
            )

        gap_map = gap_map or self._gaps.get(student_id)
        threshold = int(proactive_cfg.get("gap_recurrence_threshold", 3))
        if not attempt.correct and attempt.knowledge_point_id:
            # 知识点为主轴：按知识点定位漏洞是否复发
            gap_id = gap_id_for_kp(attempt.knowledge_point_id)
            if gap_id:
                gap = next((g for g in gap_map.gaps if g.gap_id == gap_id), None)
                if gap and gap.stats.wrong_7d >= threshold and gap.status != GapStatus.mastered:
                    msg = (
                        f"漏洞复发提醒：{gap.title}（gap_id={gap.gap_id}）"
                        f"近 7 日已错 {gap.stats.wrong_7d} 次，建议按 active_plan 巩固。"
                    )
                    messages.append(
                        self._emit(
                            student_id,
                            event_type=LearningProactiveEventType.gap_recurrence,
                            message=msg,
                            gap_id=gap.gap_id,
                            attempt_id=attempt.attempt_id,
                        )
                    )

        exam_msg = self.check_exam_prep(student_id, emit=True)
        if exam_msg:
            messages.append(exam_msg)

        return messages

    def check_exam_prep(self, student_id: str, *, emit: bool = False) -> Optional[LearningProactiveMessage]:
        if not self._ctx.exists(student_id):
            return None
        ctx = self._ctx.get(student_id)
        if not ctx.goal or not ctx.goal.exam_at:
            return None
        days = (ctx.goal.exam_at.date() - utc_now().date()).days
        exam_days = int((self._cfg.get("proactive") or {}).get("exam_prep_days", 3))
        if days < 0 or days > exam_days:
            return None

        recent = list_proactive_messages(
            layout_for(student_id, self._data_root).proactive_log_path,
            limit=20,
        )
        today = utc_now().date()
        for r in recent:
            if r.event_type == LearningProactiveEventType.exam_prep and r.created_at.date() == today:
                return None

        message = (
            f"考前提醒：距离考试还有 {days} 天。"
            "建议生成 study_plan 并完成冲刺包（remediation/exam_crunch_plan）。"
        )
        if not emit:
            return LearningProactiveMessage(
                event_id=_event_id(),
                event_type=LearningProactiveEventType.exam_prep,
                student_id=student_id,
                created_at=utc_now(),
                message=message,
                delivered=not self._is_suppressed(student_id),
                suppressed=self._is_suppressed(student_id),
            )
        return self._emit(
            student_id,
            event_type=LearningProactiveEventType.exam_prep,
            message=message,
        )

    def list_messages(self, student_id: str, limit: int = 20) -> list[LearningProactiveMessage]:
        path = layout_for(student_id, self._data_root).proactive_log_path
        return list_proactive_messages(path, limit=limit)
