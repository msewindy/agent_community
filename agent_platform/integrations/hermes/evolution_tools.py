"""Hermes evolution hooks + tools — C7 Phase 2–4."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_platform.integrations.hermes.tools import bootstrap_agent_platform

logger = logging.getLogger(__name__)

_svc = None


def _get_evolution_service():
    global _svc
    bootstrap_agent_platform()
    if _svc is None:
        from agent_platform.evolution.service import get_evolution_service

        _svc = get_evolution_service()
    return _svc


def _tool_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def pre_llm_recall_hook(**kwargs: Any) -> dict[str, str] | None:
    """Inject recalled skills + curriculum into the current turn (Hermes pre_llm_call)."""
    user_message = str(kwargs.get("user_message") or "")
    if not user_message.strip():
        return None
    try:
        ctx = _get_evolution_service().format_evolution_context_for_prompt(user_message)
    except Exception as e:
        logger.warning("evolution pre_llm_recall failed: %s", e)
        return None
    if not ctx:
        return None
    return {"context": ctx}


def post_llm_evolve_hook(**kwargs: Any) -> None:
    """Persist L1 experience after each successful turn (Hermes post_llm_call)."""
    user_message = str(kwargs.get("user_message") or "")
    assistant_response = str(kwargs.get("assistant_response") or "")
    if not user_message.strip() or not assistant_response.strip():
        return
    try:
        result = _get_evolution_service().on_turn_complete(user_message, assistant_response)
        logger.info(
            "evolution post_llm: stored=%s skills=%s",
            result.get("stored"),
            result.get("skills_generated"),
        )
    except Exception as e:
        logger.warning("evolution post_llm failed: %s", e)


def agent_evolution_recall(args: dict) -> str:
    """Search synthesized skills for the query."""
    query = str(args.get("query") or "").strip()
    if not query:
        return _tool_result({"success": False, "error": "query required"})
    svc = _get_evolution_service()
    skills = svc.recall_skills(query)
    return _tool_result(
        {
            "success": True,
            "count": len(skills),
            "skills": [
                {
                    "name": s.name,
                    "topic": s.topic,
                    "triggers": s.triggers,
                    "procedure": s.procedure[:500],
                    "confidence": s.confidence,
                }
                for s in skills
            ],
            "prompt_context": svc.format_recall_for_prompt(query),
        }
    )


def agent_evolution_curriculum(args: dict) -> str:
    """Return Voyager-style next practice suggestions from L1/L2 state."""
    svc = _get_evolution_service()
    plan, prompt_context = svc.curriculum_for_tool()
    return _tool_result(
        {
            "success": True,
            "count": len(plan.items),
            "generated_by": plan.generated_by,
            "items": [
                {
                    "kind": i.kind.value,
                    "topic": i.topic,
                    "title": i.title,
                    "rationale": i.rationale,
                    "suggested_prompt": i.suggested_prompt,
                    "priority": i.priority,
                    "related_skill": i.related_skill,
                }
                for i in plan.items
            ],
            "prompt_context": prompt_context,
            "logged": bool(plan.items),
        }
    )


def agent_evolution_status(args: dict) -> str:
    """Return evolution store counts."""
    svc = _get_evolution_service()
    exps = svc.store.list_experiences()
    skills = svc.store.list_skills()
    plan = svc.propose_curriculum_plan()
    log_rows = svc.store.list_curriculum_log(limit=20)
    return _tool_result(
        {
            "success": True,
            "experience_count": len(exps),
            "skill_count": len(skills),
            "skills": [s.name for s in skills[:20]],
            "curriculum_suggestions": len(plan.items),
            "curriculum_log_count": len(log_rows),
            "curriculum_log_recent": [
                {
                    "ts": row.ts,
                    "source": row.source.value,
                    "injected": row.injected,
                    "item_count": row.item_count,
                    "kinds": [i.kind.value for i in row.items],
                }
                for row in log_rows[-5:]
            ],
        }
    )


def check_evolution_available(**kwargs) -> bool:
    return True


AGENT_EVOLUTION_RECALL_SCHEMA = {
    "name": "agent_evolution_recall",
    "description": (
        "Search self-evolved skills (C7) synthesized from past successful turns. "
        "Use when the user repeats a workflow or asks how something was done before."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Task or topic to match against skill triggers."},
        },
        "required": ["query"],
    },
}

AGENT_EVOLUTION_CURRICULUM_SCHEMA = {
    "name": "agent_evolution_curriculum",
    "description": (
        "Suggest next workflows to practice (C7 curriculum). "
        "Use when the user asks what to learn next or wants to improve recurring tasks."
    ),
    "parameters": {"type": "object", "properties": {}, "required": []},
}

AGENT_EVOLUTION_STATUS_SCHEMA = {
    "name": "agent_evolution_status",
    "description": "Report evolution layer stats: experiences, skills, curriculum suggestions.",
    "parameters": {"type": "object", "properties": {}, "required": []},
}


def register_evolution_hermes_tools(ctx) -> None:
    bootstrap_agent_platform()

    ctx.register_hook("pre_llm_call", pre_llm_recall_hook)
    ctx.register_hook("post_llm_call", post_llm_evolve_hook)

    ctx.register_tool(
        name="agent_evolution_recall",
        toolset="agent_evolution",
        schema=AGENT_EVOLUTION_RECALL_SCHEMA,
        handler=lambda args, **kw: agent_evolution_recall(args),
        check_fn=check_evolution_available,
        emoji="🧬",
    )
    ctx.register_tool(
        name="agent_evolution_curriculum",
        toolset="agent_evolution",
        schema=AGENT_EVOLUTION_CURRICULUM_SCHEMA,
        handler=lambda args, **kw: agent_evolution_curriculum(args),
        check_fn=check_evolution_available,
        emoji="🎯",
    )
    ctx.register_tool(
        name="agent_evolution_status",
        toolset="agent_evolution",
        schema=AGENT_EVOLUTION_STATUS_SCHEMA,
        handler=lambda args, **kw: agent_evolution_status(args),
        check_fn=check_evolution_available,
        emoji="📈",
    )
    logger.info(
        "agent-evolution: registered hooks + tools (recall, curriculum, status)"
    )
