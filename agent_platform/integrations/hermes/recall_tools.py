"""Hermes agent_combined_recall — M2 memory + M3 wiki (M3 D9)."""

from __future__ import annotations

import json
import logging
from typing import Any

from agent_platform.integrations.hermes.tools import (
    _tool_error,
    _tool_result,
    bootstrap_agent_platform,
)

logger = logging.getLogger(__name__)


def _resolve_services():
    """Use Hermes plugin hooks when patched (smoke/tests), else default services."""
    bootstrap_agent_platform()
    from agent_platform.memory.service import MemoryService
    from agent_platform.wiki.service import WikiService

    mem_svc = MemoryService()
    wiki_svc = WikiService()
    try:
        from agent_platform.integrations.hermes import tools as mt
        from agent_platform.integrations.hermes import wiki_tools as wt

        if getattr(mt, "_get_service", None):
            mem_svc = mt._get_service()
        if getattr(wt, "_get_wiki_service", None):
            wiki_svc = wt._get_wiki_service()
    except ImportError:
        pass
    return mem_svc, wiki_svc


def _run_combined_recall(args: dict, **kwargs):
    from agent_platform.integrations.recall import combined_recall

    query = (args.get("query") or "").strip()
    if not query:
        raise ValueError("missing query")
    tid = args.get("trace_id")
    if not tid:
        sid = kwargs.get("current_session_id") or kwargs.get("session_id")
        if sid:
            tid = f"hermes-{sid}"
    mem_svc, wiki_svc = _resolve_services()
    return combined_recall(
        query,
        device_id=args.get("device_id"),
        memory_limit=int(args.get("memory_limit", 5)),
        wiki_limit=int(args.get("wiki_limit", 5)),
        trace_id=tid,
        memory_service=mem_svc,
        wiki_service=wiki_svc,
    )


def agent_combined_recall(args: dict, **kwargs) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return _tool_error("Missing required parameter: query")
    try:
        result = _run_combined_recall(args, **kwargs)
        return _tool_result(
            {
                "success": True,
                "trace_id": result.trace_id,
                "memory_count": len(result.memory_items),
                "wiki_count": len(result.wiki_items),
                "memory": [
                    {"ref": i.ref, "title": i.title, "content": i.content[:300], "score": i.score}
                    for i in result.memory_items
                ],
                "wiki": [
                    {"ref": i.ref, "title": i.title, "content": i.content[:300], "score": i.score}
                    for i in result.wiki_items
                ],
                "prompt_context": result.prompt_context,
            }
        )
    except Exception as e:
        logger.exception("agent_combined_recall failed")
        return _tool_error(f"Combined recall failed: {e}")


def check_combined_recall_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.integrations.recall import combined_recall  # noqa: F401
        from agent_platform.memory.service import MemoryService  # noqa: F401
        from agent_platform.wiki.service import WikiService  # noqa: F401

        return True
    except Exception as e:
        logger.debug("combined recall not available: %s", e)
        return False


AGENT_COMBINED_RECALL_SCHEMA: dict[str, Any] = {
    "name": "agent_combined_recall",
    "description": (
        "Recall user preferences from memory_service (C1) AND topic knowledge from wiki_service (C2) "
        "in one call. Use before answering when both reply style and domain facts may matter. "
        "Returns prompt_context suitable for injection."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "User question or topic."},
            "memory_limit": {"type": "integer", "default": 5},
            "wiki_limit": {"type": "integer", "default": 5},
            "device_id": {"type": "string"},
        },
        "required": ["query"],
    },
}


def register_recall_hermes_tools(ctx) -> None:
    ctx.register_tool(
        name="agent_combined_recall",
        toolset="agent_recall",
        schema=AGENT_COMBINED_RECALL_SCHEMA,
        handler=lambda args, **kw: agent_combined_recall(args, **kw),
        check_fn=check_combined_recall_available,
        emoji="🔗",
    )
