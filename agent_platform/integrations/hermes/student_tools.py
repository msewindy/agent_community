"""Hermes student Jarvis tools + pre_llm hook (Phase 5)."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any

from agent_platform.integrations.hermes.tools import (
    _tool_error,
    _tool_result,
    bootstrap_agent_platform,
)

logger = logging.getLogger(__name__)

_ctx_svc = None
_gap_svc = None
_att_svc = None
_push_svc = None
_plan_svc = None
_proactive_svc = None
_bank_svc = None
_triage_svc = None


def _student_data_root() -> Path | None:
    raw = os.environ.get("STUDENT_JARVIS_DATA_ROOT", "").strip()
    return Path(raw) if raw else None


def _require_student_id(args: dict, kwargs: dict) -> str | None:
    bootstrap_agent_platform()
    from agent_platform.learning._config import resolve_student_id

    sid = resolve_student_id(args, kwargs)
    if not sid:
        return None
    return sid


def _get_ctx_svc():
    global _ctx_svc
    bootstrap_agent_platform()
    if _ctx_svc is None:
        from agent_platform.learning.student_context import StudentContextService

        _ctx_svc = StudentContextService(data_root=_student_data_root())
    return _ctx_svc


def _get_gap_svc():
    global _gap_svc
    bootstrap_agent_platform()
    if _gap_svc is None:
        from agent_platform.learning.gap_map import GapMapService

        _gap_svc = GapMapService(data_root=_student_data_root())
    return _gap_svc


def _get_att_svc():
    global _att_svc
    bootstrap_agent_platform()
    if _att_svc is None:
        from agent_platform.learning.attempt import AttemptService

        _att_svc = AttemptService(data_root=_student_data_root())
    return _att_svc


def _get_push_svc():
    global _push_svc
    bootstrap_agent_platform()
    if _push_svc is None:
        from agent_platform.learning.push_engine import PushEngineService

        _push_svc = PushEngineService(data_root=_student_data_root())
    return _push_svc


def _get_plan_svc():
    global _plan_svc
    bootstrap_agent_platform()
    if _plan_svc is None:
        from agent_platform.learning.study_plan import StudyPlanService

        _plan_svc = StudyPlanService(data_root=_student_data_root())
    return _plan_svc


def _get_learning_proactive_svc():
    global _proactive_svc
    bootstrap_agent_platform()
    if _proactive_svc is None:
        from agent_platform.learning.learning_proactive import LearningProactiveService

        _proactive_svc = LearningProactiveService(data_root=_student_data_root())
    return _proactive_svc


def _get_bank_svc():
    global _bank_svc
    bootstrap_agent_platform()
    if _bank_svc is None:
        from agent_platform.learning.question_bank import QuestionBankService

        _bank_svc = QuestionBankService()
    return _bank_svc


def _get_triage_svc():
    global _triage_svc
    bootstrap_agent_platform()
    if _triage_svc is None:
        from agent_platform.learning.photo_triage import PhotoTriageService

        _triage_svc = PhotoTriageService(data_root=_student_data_root())
    return _triage_svc


def check_student_tools_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.learning.student_context import StudentContextService  # noqa: F401

        return True
    except Exception as e:
        logger.debug("student tools not available: %s", e)
        return False


def student_context_get(args: dict, **kwargs) -> str:
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error(
            "Missing student_id (pass arg, set STUDENT_JARVIS_STUDENT_ID, or hermes.default_student_id)"
        )
    try:
        svc = _get_ctx_svc()
        ctx = svc.get(sid)
        block = svc.to_prompt_block(ctx)
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "context": ctx.model_dump(mode="json"),
                "prompt_block": block,
            }
        )
    except FileNotFoundError:
        return _tool_error(f"student context not found: {sid}")
    except Exception as e:
        logger.exception("student_context_get failed")
        return _tool_error(str(e))


def gap_map_query(args: dict, **kwargs) -> str:
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    try:
        limit = int(args.get("limit", 5))
        svc = _get_gap_svc()
        gaps = svc.query(sid, limit=limit)
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "count": len(gaps),
                "gaps": [g.model_dump(mode="json") for g in gaps],
            }
        )
    except Exception as e:
        logger.exception("gap_map_query failed")
        return _tool_error(str(e))


def attempt_submit(args: dict, **kwargs) -> str:
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    qid = (args.get("question_id") or "").strip()
    answer = args.get("answer")
    if not qid or answer is None:
        return _tool_error("Missing question_id or answer")
    try:
        result = _get_att_svc().submit(sid, qid, str(answer))
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "attempt_id": result.attempt_id,
                "correct": result.correct,
                "explanation": result.explanation,
                "error_code": result.error_code,
                "expected_answer": result.expected_answer,
                "session_stats": result.session_stats.model_dump(mode="json"),
                "proactive": [m.model_dump(mode="json") for m in result.proactive],
            }
        )
    except FileNotFoundError as e:
        return _tool_error(str(e))
    except KeyError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("attempt_submit failed")
        return _tool_error(str(e))


def attempt_submit_freeform(args: dict, **kwargs) -> str:
    """Record an out-of-bank real-homework attempt. The model supplies correctness + error_code."""
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    stem = (args.get("stem") or "").strip()
    answer = args.get("answer")
    correct = args.get("correct")
    if not stem or answer is None or correct is None:
        return _tool_error("Missing stem, answer or correct")
    try:
        result = _get_att_svc().submit_freeform(
            sid,
            stem=stem,
            answer=str(answer),
            correct=bool(correct),
            error_code=args.get("error_code"),
            knowledge_point_id=args.get("knowledge_point_id"),
            expected_answer=args.get("expected_answer"),
            explanation=args.get("explanation"),
        )
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "attempt_id": result.attempt_id,
                "source": "freeform",
                "correct": result.correct,
                "error_code": result.error_code,
                "session_stats": result.session_stats.model_dump(mode="json"),
                "proactive": [m.model_dump(mode="json") for m in result.proactive],
            }
        )
    except (FileNotFoundError, ValueError) as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("attempt_submit_freeform failed")
        return _tool_error(str(e))


def push_queue_peek(args: dict, **kwargs) -> str:
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    try:
        limit = int(args.get("limit", 5))
        items = _get_push_svc().peek(sid, limit=limit)
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "note": "Offline micro-plan queue; prefer questions_suggest for live practice.",
                "count": len(items),
                "items": [i.model_dump(mode="json") for i in items],
            }
        )
    except FileNotFoundError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("push_queue_peek failed")
        return _tool_error(str(e))


def questions_suggest(args: dict, **kwargs) -> str:
    """Real-time question pick by current unit / KP (preferred over push_queue_peek)."""
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    try:
        ctx = _get_ctx_svc().get(sid)
        unit_id = (args.get("unit_id") or ctx.curriculum.unit_id or "").strip()
        if not unit_id:
            return _tool_error("Missing unit_id")
        focus = (args.get("focus") or "current_unit").strip()
        kp_id = (args.get("knowledge_point_id") or "").strip() or None
        limit = int(args.get("limit", 3))

        from agent_platform.learning.kp_catalog import KpCatalogService
        from agent_platform.learning.push_engine import _recent_question_ids
        from agent_platform.learning.store import layout_for, list_attempt_paths, load_attempt

        grade_level = ctx.curriculum.grade_level
        cat = KpCatalogService()
        allowed = None
        if grade_level is not None:
            allowed = {u.unit_id for u in cat.list_units(grade_level=grade_level)}

        lay = layout_for(sid, _student_data_root())
        attempts = [load_attempt(p) for p in list_attempt_paths(lay.attempts_dir)]
        exclude = _recent_question_ids(attempts)

        bank = _get_bank_svc()
        questions = bank.suggest_questions(
            unit_id=unit_id,
            knowledge_point_id=kp_id,
            focus=focus,
            limit=limit,
            allowed_unit_ids=allowed,
            prefer_unit_id=unit_id,
            exclude_question_ids=exclude,
        )
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "unit_id": unit_id,
                "focus": focus,
                "knowledge_point_id": kp_id,
                "count": len(questions),
                "questions": [
                    {
                        "question_id": q.question_id,
                        "stem": q.stem,
                        "knowledge_point_id": q.knowledge_point_id,
                        "unit_id": q.unit_id,
                    }
                    for q in questions
                ],
            }
        )
    except FileNotFoundError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("questions_suggest failed")
        return _tool_error(str(e))


def question_get(args: dict, **kwargs) -> str:
    """Return a question's stem (and metadata) by question_id. No answer/explanation (avoid spoiling)."""
    qid = (args.get("question_id") or "").strip()
    if not qid:
        return _tool_error("Missing question_id")
    try:
        q = _get_bank_svc().get(qid)
        return _tool_result(
            {
                "success": True,
                "question_id": q.question_id,
                "unit_id": q.unit_id,
                "knowledge_point_id": q.knowledge_point_id,
                "stem": q.stem,
                "answer_type": q.answer_type,
            }
        )
    except KeyError:
        return _tool_error(f"question not found: {qid}")
    except Exception as e:
        logger.exception("question_get failed")
        return _tool_error(str(e))


def study_plan_generate(args: dict, **kwargs) -> str:
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    try:
        plan = _get_plan_svc().generate(sid)
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "plan_id": plan.plan_id,
                "duration_min": plan.duration_min,
                "skill_ids": plan.skill_ids,
                "plan": plan.model_dump(mode="json"),
            }
        )
    except FileNotFoundError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("study_plan_generate failed")
        return _tool_error(str(e))


def student_answer_gate(args: dict, **kwargs) -> str:
    text = (args.get("text") or "").strip()
    if not text:
        return _tool_error("Missing text")
    sid = _require_student_id(args, kwargs)
    try:
        from agent_platform.learning.answer_gate import StudentAnswerGate

        gaps = _get_gap_svc().query(sid, limit=10) if sid else []
        result = StudentAnswerGate().check(text, gaps)
        return _tool_result(
            {
                "success": True,
                "passed": result.passed,
                "text": result.text,
                "rewritten": result.rewritten,
                "violations": result.violations,
            }
        )
    except Exception as e:
        logger.exception("student_answer_gate failed")
        return _tool_error(str(e))


def pre_llm_student_context_hook(**kwargs: Any) -> dict[str, str] | None:
    """Inject StudentContext + gaps + AnswerGate rules before each LLM turn."""
    bootstrap_agent_platform()
    from agent_platform.learning._config import load_student_learning_config, resolve_student_id
    from agent_platform.learning.prompts import ANSWER_GATE_RULES, format_pre_llm_context
    from agent_platform.learning.student_safety import StudentSafetyService

    cfg = load_student_learning_config()
    hermes_cfg = cfg.get("hermes") or {}
    if not hermes_cfg.get("inject_system_rules", True):
        return None

    user_msg = (kwargs.get("user_message") or kwargs.get("message") or "").strip()
    if user_msg:
        safety = StudentSafetyService(cfg)
        subject = str((cfg.get("default_curriculum") or {}).get("subject", "语文或数学"))
        check = safety.check_user_message(user_msg, subject=subject)
        if not check.allowed and check.redirect_message:
            return {
                "context": ANSWER_GATE_RULES
                + "\n\n## 域外请求 — 必须拒答并拉回\n"
                + check.redirect_message
            }

    sid = resolve_student_id(kwargs=kwargs)
    if not sid:
        return {"context": ANSWER_GATE_RULES}

    try:
        ctx_svc = _get_ctx_svc()
        if not ctx_svc.exists(sid):
            return {
                "context": ANSWER_GATE_RULES
                + "\n\n（尚未初始化 StudentContext，请 CLI init 或确认 STUDENT_JARVIS_STUDENT_ID）"
            }
        ctx = ctx_svc.get(sid)
        gaps = _get_gap_svc().query(sid, limit=3)
        block = format_pre_llm_context(
            prompt_block=ctx_svc.to_prompt_block(ctx),
            gaps=gaps,
            user_message=user_msg,
        )
        try:
            from agent_platform.perception.vision_session import VisionSessionStore
            from agent_platform.perception.vision_understand import format_vision_pre_llm_block

            vision = VisionSessionStore.load_from_env()
            if vision is not None:
                block += format_vision_pre_llm_block(vision)
        except Exception as e:
            logger.debug("vision pre_llm inject skipped: %s", e)
        return {"context": block}
    except Exception as e:
        logger.warning("pre_llm_student_context failed: %s", e)
        return {"context": ANSWER_GATE_RULES}


def classify_photo(args: dict, **kwargs) -> str:
    """归类已批改作业题并分流入学情/待归类（Agent 编排调用，非前端直连）。"""
    sid = _require_student_id(args, kwargs)
    if not sid:
        return _tool_error("Missing student_id")
    raw_items = args.get("items")
    if not isinstance(raw_items, list) or not raw_items:
        return _tool_error("Missing items: list of {stem, student_answer, is_correct}")
    try:
        from agent_platform.learning.photo_triage import GradedItem

        items = []
        for it in raw_items:
            if not isinstance(it, dict):
                continue
            stem = (it.get("stem") or "").strip()
            if not stem:
                continue
            ic = it.get("is_correct")
            if ic is not None:
                ic = bool(ic)
            items.append(
                GradedItem(
                    stem=stem,
                    student_answer=str(it.get("student_answer") or ""),
                    is_correct=ic,
                )
            )
        if not items:
            return _tool_error("No valid items with stem")
        summary = _get_triage_svc().classify_and_ingest(sid, items)
        return _tool_result(
            {
                "success": True,
                "student_id": sid,
                "auto_ingested": summary.get("auto", 0),
                "pending_confirm": summary.get("confirm", 0),
                "pending_unclassified": summary.get("inbox", 0),
                "auto_attempt_ids": summary.get("auto_attempt_ids", []),
                "classified": summary.get("classified", []),
                "hint": (
                    "高置信已自动入学情；待确认/待归类的题在家长学情页「尚未归类的题」区块，"
                    "仍是学情的一部分。"
                ),
            }
        )
    except FileNotFoundError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("classify_photo failed")
        return _tool_error(str(e))


def student_safety_check(args: dict, **kwargs) -> str:
    text = (args.get("text") or args.get("message") or "").strip()
    if not text:
        return _tool_error("Missing text")
    try:
        from agent_platform.learning._config import load_student_learning_config
        from agent_platform.learning.student_safety import StudentSafetyService

        cfg = load_student_learning_config()
        subject = str(args.get("subject") or (cfg.get("default_curriculum") or {}).get("subject", "语文或数学"))
        result = StudentSafetyService(cfg).check_user_message(text, subject=subject)
        return _tool_result(
            {
                "success": True,
                "allowed": result.allowed,
                "reason_code": result.reason_code,
                "redirect_message": result.redirect_message,
            }
        )
    except Exception as e:
        logger.exception("student_safety_check failed")
        return _tool_error(str(e))


STUDENT_SAFETY_CHECK_SCHEMA = {
    "name": "student_safety_check",
    "description": "Detect off-topic student requests (games, homework ghostwriting) and return redirect message.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Student user message to check."},
            "subject": {"type": "string", "description": "Current learning subject for redirect."},
        },
        "required": ["text"],
    },
}


STUDENT_CONTEXT_GET_SCHEMA = {
    "name": "student_context_get",
    "description": "Get persisted StudentContext (unit, stage, focus, session_stats) for the student.",
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string", "description": "Student id; optional if env/config default set."},
        },
        "required": [],
    },
}

GAP_MAP_QUERY_SCHEMA = {
    "name": "gap_map_query",
    "description": "Query top learning gaps (wrong_7d, status, evidence). Required before claiming weaknesses.",
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": [],
    },
}

ATTEMPT_SUBMIT_SCHEMA = {
    "name": "attempt_submit",
    "description": "Submit an answer for grading; updates gap_map and push_queue.",
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "question_id": {"type": "string"},
            "answer": {"type": "string"},
        },
        "required": ["question_id", "answer"],
    },
}

ATTEMPT_SUBMIT_FREEFORM_SCHEMA = {
    "name": "attempt_submit_freeform",
    "description": (
        "Record a REAL homework question that is NOT in the bank (e.g. a word problem the child brought). "
        "Use this instead of attempt_submit when there is no question_id. "
        "You judge correctness and, if wrong, classify error_code from the configured taxonomy "
        "(e.g. READING_ERROR 审题列式, CARRY_ERROR 进位, BORROW_ERROR 退位, CALCULATION_ERROR 计算失误). "
        "Do NOT invent error codes."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "stem": {"type": "string", "description": "The real question text."},
            "answer": {"type": "string", "description": "The child's answer."},
            "correct": {"type": "boolean", "description": "Whether the child's answer is correct."},
            "error_code": {
                "type": "string",
                "description": "Required when correct=false; must be a configured taxonomy code.",
            },
            "knowledge_point_id": {
                "type": "string",
                "description": "Optional; the KP being practiced (useful when correct=true to credit a gap).",
            },
            "expected_answer": {"type": "string"},
            "explanation": {"type": "string"},
        },
        "required": ["stem", "answer", "correct"],
    },
}

CLASSIFY_PHOTO_SCHEMA = {
    "name": "classify_photo",
    "description": (
        "Classify graded homework items (from photo VLM) to knowledge points in the CLOSED catalog, "
        "then route: high-confidence → auto ingest to learning profile; medium → parent confirm; "
        "no match → pending unclassified (shown on parent learning profile page). "
        "Call when the student expresses intent to RECORD/REVIEW mistakes into 学情 "
        "(semantic: review graded paper, save wrong answers, consolidate weak areas — not a fixed phrase). "
        "Requires graded_homework vision context. "
        "Do NOT call for explain-only intent ('teach me', 'I don't understand this problem')."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "items": {
                "type": "array",
                "description": "Each item from the graded homework photo.",
                "items": {
                    "type": "object",
                    "properties": {
                        "stem": {"type": "string", "description": "Question text."},
                        "student_answer": {"type": "string"},
                        "is_correct": {
                            "type": "boolean",
                            "description": "Teacher mark: true=对, false=错; omit if unknown.",
                        },
                    },
                    "required": ["stem"],
                },
            },
        },
        "required": ["items"],
    },
}

PUSH_QUEUE_PEEK_SCHEMA = {
    "name": "push_queue_peek",
    "description": (
        "Peek offline micro-plan queue (legacy). For normal practice use questions_suggest instead."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "limit": {"type": "integer", "default": 5},
        },
        "required": [],
    },
}

QUESTIONS_SUGGEST_SCHEMA = {
    "name": "questions_suggest",
    "description": (
        "Suggest practice questions in real time from the question bank. "
        "Use when the student wants to practice (not when explaining new topics). "
        "Default focus=current_unit uses StudentContext unit; focus=remediation needs knowledge_point_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
            "unit_id": {"type": "string", "description": "Defaults to current unit from context."},
            "knowledge_point_id": {"type": "string", "description": "Optional KP filter or remediation target."},
            "focus": {
                "type": "string",
                "enum": ["current_unit", "remediation"],
                "description": "current_unit=new learning; remediation=weak KP drill.",
            },
            "limit": {"type": "integer", "default": 3},
        },
        "required": [],
    },
}

QUESTION_GET_SCHEMA = {
    "name": "question_get",
    "description": (
        "Fetch a question's stem (题面) and metadata by question_id. "
        "Use after questions_suggest to present a question. Does NOT return the answer."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "question_id": {"type": "string", "description": "Question id, e.g. q-g2m-002."},
        },
        "required": ["question_id"],
    },
}

STUDENT_ANSWER_GATE_SCHEMA = {
    "name": "student_answer_gate",
    "description": (
        "Validate assistant draft: mastery/gap claims must cite gap_id or attempt_id. "
        "Returns rewritten guiding text if evidence missing."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Draft assistant reply."},
            "student_id": {"type": "string"},
        },
        "required": ["text"],
    },
}


STUDY_PLAN_GENERATE_SCHEMA = {
    "name": "study_plan_generate",
    "description": (
        "Generate a 20-30 minute micro study plan from Top gaps; sets context.focus.active_plan_id."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "student_id": {"type": "string"},
        },
        "required": [],
    },
}


def register_student_hermes_tools(ctx) -> None:
    bootstrap_agent_platform()
    ctx.register_hook("pre_llm_call", pre_llm_student_context_hook)
    ctx.register_tool(
        name="student_context_get",
        toolset="agent_student",
        schema=STUDENT_CONTEXT_GET_SCHEMA,
        handler=lambda args, **kw: student_context_get(args, **kw),
        check_fn=check_student_tools_available,
        emoji="🎓",
    )
    ctx.register_tool(
        name="gap_map_query",
        toolset="agent_student",
        schema=GAP_MAP_QUERY_SCHEMA,
        handler=lambda args, **kw: gap_map_query(args, **kw),
        check_fn=check_student_tools_available,
        emoji="🗺️",
    )
    ctx.register_tool(
        name="attempt_submit",
        toolset="agent_student",
        schema=ATTEMPT_SUBMIT_SCHEMA,
        handler=lambda args, **kw: attempt_submit(args, **kw),
        check_fn=check_student_tools_available,
        emoji="✏️",
    )
    ctx.register_tool(
        name="attempt_submit_freeform",
        toolset="agent_student",
        schema=ATTEMPT_SUBMIT_FREEFORM_SCHEMA,
        handler=lambda args, **kw: attempt_submit_freeform(args, **kw),
        check_fn=check_student_tools_available,
        emoji="📝",
    )
    ctx.register_tool(
        name="classify_photo",
        toolset="agent_student",
        schema=CLASSIFY_PHOTO_SCHEMA,
        handler=lambda args, **kw: classify_photo(args, **kw),
        check_fn=check_student_tools_available,
        emoji="📷",
    )
    ctx.register_tool(
        name="questions_suggest",
        toolset="agent_student",
        schema=QUESTIONS_SUGGEST_SCHEMA,
        handler=lambda args, **kw: questions_suggest(args, **kw),
        check_fn=check_student_tools_available,
        emoji="🎯",
    )
    ctx.register_tool(
        name="push_queue_peek",
        toolset="agent_student",
        schema=PUSH_QUEUE_PEEK_SCHEMA,
        handler=lambda args, **kw: push_queue_peek(args, **kw),
        check_fn=check_student_tools_available,
        emoji="📋",
    )
    ctx.register_tool(
        name="question_get",
        toolset="agent_student",
        schema=QUESTION_GET_SCHEMA,
        handler=lambda args, **kw: question_get(args, **kw),
        check_fn=check_student_tools_available,
        emoji="❓",
    )
    ctx.register_tool(
        name="student_answer_gate",
        toolset="agent_student",
        schema=STUDENT_ANSWER_GATE_SCHEMA,
        handler=lambda args, **kw: student_answer_gate(args, **kw),
        check_fn=check_student_tools_available,
        emoji="🛡️",
    )
    ctx.register_tool(
        name="student_safety_check",
        toolset="agent_student",
        schema=STUDENT_SAFETY_CHECK_SCHEMA,
        handler=lambda args, **kw: student_safety_check(args, **kw),
        check_fn=check_student_tools_available,
        emoji="🚫",
    )
    ctx.register_tool(
        name="study_plan_generate",
        toolset="agent_student",
        schema=STUDY_PLAN_GENERATE_SCHEMA,
        handler=lambda args, **kw: study_plan_generate(args, **kw),
        check_fn=check_student_tools_available,
        emoji="📝",
    )
    logger.info(
        "agent-student: pre_llm hook + student_context_get, gap_map_query, "
        "attempt_submit, attempt_submit_freeform, questions_suggest, push_queue_peek, question_get, "
        "student_answer_gate, student_safety_check, study_plan_generate"
    )
