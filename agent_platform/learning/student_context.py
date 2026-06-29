"""StudentContextService — learning situation aggregate (Phase 1)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    ContextFlags,
    ContextFocus,
    Curriculum,
    PipelineStage,
    SessionStats,
    StudentContext,
    StudentContextInit,
    StudentContextPatch,
    utc_now,
)
from agent_platform.learning.store import layout_for, load_context, save_context
from agent_platform.memory.trace import new_trace_id

_STAGE_LABELS = {
    PipelineStage.onboarding: "入门熟悉",
    PipelineStage.learning: "新知学习",
    PipelineStage.practice: "巩固练习",
    PipelineStage.remediation: "漏洞补救",
    PipelineStage.review: "阶段复习",
    PipelineStage.exam_prep: "考前冲刺",
}


class StudentContextService:
    def __init__(self, config: Optional[dict] = None, data_root: Optional[Path] = None) -> None:
        self._cfg = config or load_student_learning_config()
        self._data_root = data_root

    def _layout(self, student_id: str):
        return layout_for(student_id, self._data_root)

    def exists(self, student_id: str) -> bool:
        return self._layout(student_id).context_path.is_file()

    def get(self, student_id: str) -> StudentContext:
        lay = self._layout(student_id)
        if not lay.context_path.is_file():
            raise FileNotFoundError(f"student context not found: {student_id}")
        return load_context(lay.context_path)

    def init(self, student_id: str, body: StudentContextInit) -> StudentContext:
        lay = self._layout(student_id)
        if lay.context_path.is_file():
            raise FileExistsError(f"student context already exists: {student_id}")
        lay.ensure_student_dir()
        now = utc_now()
        ctx = StudentContext(
            student_id=student_id,
            updated_at=now,
            curriculum=body.curriculum,
            pipeline_stage=body.pipeline_stage,
            focus=ContextFocus(),
            goal=body.goal,
            flags=body.flags or ContextFlags(),
            trace_id=new_trace_id(),
        )
        save_context(lay.context_path, ctx)
        return ctx

    def init_from_defaults(self, student_id: str, unit_id: Optional[str] = None) -> StudentContext:
        defaults = self._cfg.get("default_curriculum") or {}
        cur = dict(defaults)
        if unit_id:
            cur["unit_id"] = unit_id
        stage_raw = (self._cfg.get("defaults") or {}).get("pipeline_stage", "onboarding")
        return self.init(
            student_id,
            StudentContextInit(
                curriculum=Curriculum.model_validate(cur),
                pipeline_stage=PipelineStage(stage_raw),
            ),
        )

    def patch(self, student_id: str, patch: StudentContextPatch) -> StudentContext:
        current = self.get(student_id)
        data = current.model_dump()
        for key, val in patch.model_dump(exclude_unset=True).items():
            if val is not None:
                data[key] = val
        data["updated_at"] = utc_now()
        data["trace_id"] = new_trace_id()
        updated = StudentContext.model_validate(data)
        save_context(self._layout(student_id).context_path, updated)
        return updated

    def merge_focus(
        self,
        student_id: str,
        *,
        top_gap_ids: list[str],
        queue_head_question_ids: list[str],
        active_plan_id: Optional[str] = None,
    ) -> StudentContext:
        """Pipeline API (Phase 3/4): update focus pointers only."""
        focus = ContextFocus(
            top_gap_ids=top_gap_ids[:3],
            queue_head_question_ids=queue_head_question_ids[:5],
            active_plan_id=active_plan_id,
        )
        return self.patch(student_id, StudentContextPatch(focus=focus))

    def merge_session_stats(
        self,
        student_id: str,
        *,
        last_activity_at=None,
        attempts_today: Optional[int] = None,
        correct_rate_7d: Optional[float] = None,
    ) -> StudentContext:
        """Pipeline API (Phase 2+)."""
        current = self.get(student_id)
        base = current.session_stats or SessionStats()
        stats = SessionStats(
            last_activity_at=last_activity_at or base.last_activity_at or utc_now(),
            attempts_today=attempts_today if attempts_today is not None else base.attempts_today,
            correct_rate_7d=correct_rate_7d if correct_rate_7d is not None else base.correct_rate_7d,
        )
        return self.patch(student_id, StudentContextPatch(session_stats=stats))

    def to_prompt_block(self, ctx: Optional[StudentContext] = None, student_id: Optional[str] = None) -> str:
        if ctx is None:
            if not student_id:
                raise ValueError("ctx or student_id required")
            ctx = self.get(student_id)
        stage = _STAGE_LABELS.get(ctx.pipeline_stage, str(ctx.pipeline_stage))
        lines = [
            "## 学生学习情境（StudentContext，不可被对话随意覆盖）",
            f"- 学生：{ctx.student_id}",
            f"- 学科/单元：{ctx.curriculum.subject} · {ctx.curriculum.unit_title}（{ctx.curriculum.unit_id}）",
            f"- 年级：{ctx.curriculum.grade}",
            f"- 当前阶段：{stage}（{ctx.pipeline_stage.value}）",
        ]
        if ctx.curriculum.textbook_ref:
            lines.append(f"- 教材：{ctx.curriculum.textbook_ref}")
        if ctx.goal and ctx.goal.label:
            lines.append(f"- 目标：{ctx.goal.label}")
        if ctx.focus.top_gap_ids:
            lines.append(f"- 优先漏洞：{', '.join(ctx.focus.top_gap_ids)}")
        if ctx.session_stats and ctx.session_stats.correct_rate_7d is not None:
            pct = int(ctx.session_stats.correct_rate_7d * 100)
            lines.append(f"- 近7日正确率：约 {pct}%")
        return "\n".join(lines)
