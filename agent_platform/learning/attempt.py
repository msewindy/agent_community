"""Attempt submission service (Phase 2)."""

from __future__ import annotations

import secrets
from datetime import timedelta
from pathlib import Path
from typing import Optional

from agent_platform.learning.contracts import (
    AttemptRecord,
    AttemptSubmitResult,
    SessionStats,
    utc_now,
)
from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.gap_map import GapMapUpdater
from agent_platform.learning.grader import Grader
from agent_platform.learning.kp_catalog import GradeBoundaryError, KpCatalogService
from agent_platform.learning.evolution_bridge import LearningEvolutionBridge
from agent_platform.learning.learning_proactive import LearningProactiveService
from agent_platform.learning.push_engine import PushEngineService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.store import (
    layout_for,
    list_attempt_paths,
    load_attempt,
    save_attempt,
)
from agent_platform.learning.student_context import StudentContextService
from agent_platform.memory.trace import new_trace_id


def new_attempt_id(now=None) -> str:
    ts = now or utc_now()
    suffix = secrets.token_hex(3)
    return ts.strftime("att-%Y%m%d-%H%M%S-") + suffix


def compute_session_stats(attempts: list[AttemptRecord], now=None) -> SessionStats:
    now = now or utc_now()
    today = now.date()
    window_start = now - timedelta(days=7)

    attempts_today = sum(1 for a in attempts if a.submitted_at.date() == today)
    in_window = [a for a in attempts if a.submitted_at >= window_start]
    if in_window:
        correct_rate = sum(1 for a in in_window if a.correct) / len(in_window)
        last_activity = max(a.submitted_at for a in in_window)
    else:
        correct_rate = None
        last_activity = now

    return SessionStats(
        last_activity_at=last_activity,
        attempts_today=attempts_today,
        correct_rate_7d=correct_rate,
    )


class AttemptService:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        question_bank: Optional[QuestionBankService] = None,
        grader: Optional[Grader] = None,
        context_svc: Optional[StudentContextService] = None,
        gap_updater: Optional[GapMapUpdater] = None,
        push_engine: Optional[PushEngineService] = None,
        learning_proactive: Optional[LearningProactiveService] = None,
        evolution_bridge: Optional[LearningEvolutionBridge] = None,
        catalog: Optional[KpCatalogService] = None,
    ) -> None:
        cfg = load_student_learning_config()
        push_cfg = cfg.get("push") or {}
        self._enforce_grade_boundary = bool(push_cfg.get("enforce_grade_boundary", False))
        self._data_root = data_root
        self._bank = question_bank or QuestionBankService()
        self._catalog = catalog or KpCatalogService(config=cfg)
        self._grader = grader or Grader()
        self._ctx = context_svc or StudentContextService(data_root=data_root)
        self._gap = gap_updater or GapMapUpdater(
            context_svc=self._ctx,
            data_root=data_root,
        )
        self._push = push_engine or PushEngineService(
            data_root=data_root,
            bank=self._bank,
            context_svc=self._ctx,
        )
        self._proactive = learning_proactive or LearningProactiveService(
            data_root=data_root,
            ctx_svc=self._ctx,
        )
        self._evolution = evolution_bridge or LearningEvolutionBridge(
            data_root=data_root,
        )

    def _layout(self, student_id: str):
        return layout_for(student_id, self._data_root)

    def _load_all_attempts(self, student_id: str) -> list[AttemptRecord]:
        lay = self._layout(student_id)
        return [load_attempt(p) for p in list_attempt_paths(lay.attempts_dir)]

    def submit(self, student_id: str, question_id: str, answer: str) -> AttemptSubmitResult:
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")

        question = self._bank.get(question_id)
        ctx = self._ctx.get(student_id)
        if self._enforce_grade_boundary:
            grade_level = ctx.curriculum.grade_level
            if grade_level is None:
                grade_level = self._catalog.resolve_grade_level(ctx.curriculum.grade)
            try:
                self._catalog.assert_student_may_access_unit(grade_level, question.unit_id)
            except GradeBoundaryError as e:
                raise ValueError(str(e)) from e

        grade = self._grader.grade(question, answer)
        now = utc_now()
        attempt_id = new_attempt_id(now)

        record = AttemptRecord(
            attempt_id=attempt_id,
            student_id=student_id,
            question_id=question_id,
            unit_id=question.unit_id,
            submitted_at=now,
            answer_raw=answer,
            answer_normalized=grade.answer_normalized,
            correct=grade.correct,
            expected_answer=grade.expected_answer,
            explanation=grade.explanation,
            error_code=grade.error_code,
            knowledge_point_id=question.knowledge_point_id,
            trace_id=new_trace_id(),
        )

        lay = self._layout(student_id)
        lay.ensure_student_dir()
        save_attempt(lay.attempt_path(attempt_id), record)

        attempts = self._load_all_attempts(student_id)
        stats = compute_session_stats(attempts, now)
        self._ctx.merge_session_stats(
            student_id,
            last_activity_at=stats.last_activity_at,
            attempts_today=stats.attempts_today,
            correct_rate_7d=stats.correct_rate_7d,
        )

        gap_map = self._gap.apply_after_attempt(
            student_id,
            attempts,
            ctx.curriculum.unit_id,
            sync_focus=False,
        )
        self._push.rebuild(student_id, gap_map=gap_map, sync_focus=True)

        proactive_msgs = self._proactive.on_attempt(
            student_id,
            record,
            gap_map=gap_map,
        )
        promotions = self._evolution.evaluate_after_attempt(student_id, gap_map)

        return AttemptSubmitResult(
            attempt_id=attempt_id,
            correct=grade.correct,
            explanation=grade.explanation,
            error_code=grade.error_code,
            expected_answer=grade.expected_answer,
            session_stats=stats,
            proactive=proactive_msgs,
            skill_promotions=promotions,
        )

    def submit_freeform(
        self,
        student_id: str,
        stem: str,
        answer: str,
        correct: bool,
        error_code: Optional[str] = None,
        knowledge_point_id: Optional[str] = None,
        expected_answer: Optional[str] = None,
        explanation: Optional[str] = None,
        source: str = "freeform",
    ) -> AttemptSubmitResult:
        """Record an out-of-bank (real homework) attempt. Correctness + error_code come from the LLM,
        not the deterministic grader. error_code is whitelisted against the configured taxonomy.
        """
        if not self._ctx.exists(student_id):
            raise FileNotFoundError(f"student context not found: {student_id}")
        if not (stem or "").strip():
            raise ValueError("Missing stem")

        from agent_platform.learning.taxonomy import TaxonomyService

        cfg = load_student_learning_config()
        valid_codes = set((cfg.get("error_taxonomy") or {}).get("codes", {}).keys())
        tax = TaxonomyService(cfg)

        kp = (knowledge_point_id or "").strip()
        norm_error: Optional[str] = None
        if not correct:
            # 知识点为主轴：判错只要求「挂得上知识点」；错因码可选（提供则须在白名单内）
            code = (error_code or "").strip()
            if code:
                if code not in valid_codes:
                    raise ValueError(
                        f"error_code (if provided) must be one of {sorted(valid_codes)} for an "
                        f"incorrect freeform attempt; got {error_code!r}"
                    )
                norm_error = code
                # 未显式传 kp 时，由错因表推导规范 KP（向后兼容旧调用）
                if not kp:
                    kp = tax.lookup(code).knowledge_point_id
            if not kp:
                raise ValueError(
                    "an incorrect freeform attempt requires knowledge_point_id "
                    "(or a valid error_code to derive it)"
                )
        if not kp:
            kp = "freeform-unspecified"

        ctx = self._ctx.get(student_id)
        now = utc_now()
        attempt_id = new_attempt_id(now)
        answer_str = str(answer)

        record = AttemptRecord(
            attempt_id=attempt_id,
            student_id=student_id,
            question_id=f"freeform-{now.strftime('%Y%m%d-%H%M%S')}-{secrets.token_hex(2)}",
            unit_id=ctx.curriculum.unit_id,
            submitted_at=now,
            answer_raw=answer_str,
            answer_normalized=answer_str.strip(),
            correct=correct,
            expected_answer=(expected_answer or "").strip(),
            explanation=(explanation or "").strip(),
            error_code=norm_error,
            knowledge_point_id=kp,
            trace_id=new_trace_id(),
            source=(source or "freeform").strip() or "freeform",
        )

        lay = self._layout(student_id)
        lay.ensure_student_dir()
        save_attempt(lay.attempt_path(attempt_id), record)

        attempts = self._load_all_attempts(student_id)
        stats = compute_session_stats(attempts, now)
        self._ctx.merge_session_stats(
            student_id,
            last_activity_at=stats.last_activity_at,
            attempts_today=stats.attempts_today,
            correct_rate_7d=stats.correct_rate_7d,
        )

        gap_map = self._gap.apply_after_attempt(
            student_id,
            attempts,
            ctx.curriculum.unit_id,
            sync_focus=False,
        )
        self._push.rebuild(student_id, gap_map=gap_map, sync_focus=True)
        proactive_msgs = self._proactive.on_attempt(student_id, record, gap_map=gap_map)
        promotions = self._evolution.evaluate_after_attempt(student_id, gap_map)

        return AttemptSubmitResult(
            attempt_id=attempt_id,
            correct=correct,
            explanation=record.explanation,
            error_code=norm_error,
            expected_answer=record.expected_answer,
            session_stats=stats,
            proactive=proactive_msgs,
            skill_promotions=promotions,
        )

    def list(self, student_id: str, limit: int = 50) -> list[AttemptRecord]:
        attempts = self._load_all_attempts(student_id)
        return attempts[:limit]

    def get(self, student_id: str, attempt_id: str) -> AttemptRecord:
        path = self._layout(student_id).attempt_path(attempt_id)
        if not path.is_file():
            raise FileNotFoundError(f"attempt not found: {attempt_id}")
        record = load_attempt(path)
        if record.student_id != student_id:
            raise FileNotFoundError(f"attempt not found: {attempt_id}")
        return record
