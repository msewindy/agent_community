"""Study plan generation from Top gaps (Phase 6)."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import GapStatus, StudyPlan, StudyPlanStep, utc_now
from agent_platform.learning.gap_map import GapMapService, top_gap_ids
from agent_platform.learning.push_engine import PushEngineService
from agent_platform.learning.remediation_skills import load_remediation_skills, skill_for_error_code
from agent_platform.learning.store import layout_for, save_study_plan
from agent_platform.learning.student_context import StudentContextService


def new_plan_id(now=None) -> str:
    ts = now or utc_now()
    return ts.strftime("plan-%Y%m%d-%H%M%S-") + secrets.token_hex(3)


class StudyPlanService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        gap_svc: Optional[GapMapService] = None,
        ctx_svc: Optional[StudentContextService] = None,
        push_svc: Optional[PushEngineService] = None,
    ) -> None:
        self._cfg = load_student_learning_config()
        self._data_root = data_root
        self._gaps = gap_svc or GapMapService(data_root=data_root)
        self._ctx = ctx_svc or StudentContextService(data_root=data_root, config=self._cfg)
        self._push = push_svc or PushEngineService(data_root=data_root, context_svc=self._ctx)

    def generate(self, student_id: str) -> StudyPlan:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        ctx = self._ctx.get(student_id)
        gap_map = self._gaps.get(student_id)
        eligible = [
            g
            for g in gap_map.gaps
            if g.status in (GapStatus.active, GapStatus.improving)
            and g.gap_id in top_gap_ids(gap_map.gaps)
        ]
        if not eligible:
            eligible = [
                g
                for g in gap_map.gaps
                if g.status in (GapStatus.active, GapStatus.improving)
            ][:2]

        plan_cfg = self._cfg.get("study_plan") or {}
        target_min = int(plan_cfg.get("duration_min", 25))
        floor = int(plan_cfg.get("duration_min_floor", 20))
        ceiling = int(plan_cfg.get("duration_min_ceiling", 30))
        target_min = max(floor, min(target_min, ceiling))

        steps: list[StudyPlanStep] = []
        skill_ids: list[str] = []
        gap_ids: list[str] = []
        order = 1

        exam_skill = load_remediation_skills().get("remediation/exam_crunch_plan")
        if ctx.goal and ctx.goal.exam_at:
            days = (ctx.goal.exam_at.date() - utc_now().date()).days
            exam_days = int((self._cfg.get("proactive") or {}).get("exam_prep_days", 3))
            if 0 <= days <= exam_days and exam_skill:
                steps.append(
                    StudyPlanStep(
                        order=order,
                        title=exam_skill.title,
                        duration_min=min(exam_skill.duration_min, 8),
                        skill_id=exam_skill.skill_id,
                        instructions=exam_skill.procedure.strip(),
                    )
                )
                skill_ids.append(exam_skill.skill_id)
                order += 1

        for gap in eligible[:2]:
            gap_ids.append(gap.gap_id)
            skill = skill_for_error_code(gap.error_code)
            if skill.skill_id not in skill_ids:
                skill_ids.append(skill.skill_id)
            steps.append(
                StudyPlanStep(
                    order=order,
                    title=f"{skill.title} · {gap.title}",
                    duration_min=skill.duration_min,
                    skill_id=skill.skill_id,
                    gap_id=gap.gap_id,
                    instructions=skill.procedure.strip(),
                )
            )
            order += 1

        if not steps:
            fallback = load_remediation_skills()["remediation/socratic_hint_flow"]
            steps.append(
                StudyPlanStep(
                    order=1,
                    title=fallback.title,
                    duration_min=fallback.duration_min,
                    skill_id=fallback.skill_id,
                    instructions=fallback.procedure.strip(),
                )
            )
            skill_ids.append(fallback.skill_id)

        practice_min = max(5, target_min - sum(s.duration_min for s in steps))
        queue = self._push.peek(student_id, limit=3)
        qids = [i.question_id for i in queue[:3]]
        practice_note = f"完成 push 队头题目：{', '.join(qids)}" if qids else "完成 3 道单元练习题"
        steps.append(
            StudyPlanStep(
                order=order,
                title="巩固练习",
                duration_min=practice_min,
                skill_id="remediation/procedure_checklist",
                gap_id=gap_ids[0] if gap_ids else None,
                instructions=practice_note,
            )
        )
        if "remediation/procedure_checklist" not in skill_ids:
            skill_ids.append("remediation/procedure_checklist")

        duration = sum(s.duration_min for s in steps)
        if duration > ceiling:
            overflow = duration - ceiling
            steps[-1].duration_min = max(5, steps[-1].duration_min - overflow)
            duration = sum(s.duration_min for s in steps)

        now = utc_now()
        plan = StudyPlan(
            plan_id=new_plan_id(now),
            student_id=student_id,
            created_at=now,
            duration_min=duration,
            gap_ids=gap_ids,
            skill_ids=skill_ids,
            steps=steps,
        )

        lay = layout_for(student_id, self._data_root)
        lay.ensure_student_dir()
        save_study_plan(lay.plan_path(plan.plan_id), plan)

        current = self._ctx.get(student_id)
        self._ctx.merge_focus(
            student_id,
            top_gap_ids=list(current.focus.top_gap_ids),
            queue_head_question_ids=list(current.focus.queue_head_question_ids),
            active_plan_id=plan.plan_id,
        )
        return plan

    def get(self, student_id: str, plan_id: str) -> StudyPlan:
        from agent_platform.learning.store import load_study_plan

        path = layout_for(student_id, self._data_root).plan_path(plan_id)
        if not path.is_file():
            raise FileNotFoundError(f"study plan not found: {plan_id}")
        return load_study_plan(path)
