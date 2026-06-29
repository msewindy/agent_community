"""Pilot KPI report for Student Jarvis (Phase 7)."""

from __future__ import annotations

from datetime import timedelta
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import GapStatus, LearningKpiReport, utc_now
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.push_engine import PushEngineService
from agent_platform.learning.store import layout_for, list_attempt_paths, load_attempt
from agent_platform.learning.student_context import StudentContextService


class LearningKpiService:
    def __init__(self, data_root: Optional[Path] = None) -> None:
        self._data_root = data_root
        self._ctx = StudentContextService(data_root=data_root)
        self._gaps = GapMapService(data_root=data_root)
        self._push = PushEngineService(data_root=data_root, context_svc=self._ctx)

    def _load_attempts(self, student_id: str, days: int):
        lay = layout_for(student_id, self._data_root)
        window_start = utc_now() - timedelta(days=days)
        attempts = [load_attempt(p) for p in list_attempt_paths(lay.attempts_dir)]
        return [a for a in attempts if a.submitted_at >= window_start]

    def build_report(self, student_id: str, period_days: int = 90) -> LearningKpiReport:
        attempts = self._load_attempts(student_id, period_days)
        gap_map = self._gaps.get(student_id)

        correct_rate = None
        re_error_rate = None
        if attempts:
            correct_rate = sum(1 for a in attempts if a.correct) / len(attempts)
            wrong = [a for a in attempts if not a.correct and a.error_code]
            if wrong:
                repeat = 0
                seen_codes: set[str] = set()
                for a in sorted(wrong, key=lambda x: x.submitted_at):
                    if a.error_code in seen_codes:
                        repeat += 1
                    seen_codes.add(a.error_code)
                re_error_rate = repeat / len(wrong)

        queue = self._push.get_queue(student_id)
        queue_qids = {i.question_id for i in queue.items}
        if not queue_qids and self._ctx.exists(student_id):
            ctx = self._ctx.get(student_id)
            queue_qids = set(ctx.focus.queue_head_question_ids)
        queue_completion_rate = None
        if queue_qids:
            correct_qids = {a.question_id for a in attempts if a.correct}
            queue_completion_rate = len(queue_qids & correct_qids) / len(queue_qids)

        mastered = sum(1 for g in gap_map.gaps if g.status == GapStatus.mastered)
        active = sum(
            1 for g in gap_map.gaps if g.status in (GapStatus.active, GapStatus.improving)
        )

        return LearningKpiReport(
            student_id=student_id,
            period_days=period_days,
            generated_at=utc_now(),
            attempts_total=len(attempts),
            correct_rate=correct_rate,
            re_error_rate=re_error_rate,
            queue_completion_rate=queue_completion_rate,
            gaps_mastered=mastered,
            gaps_active=active,
        )
