"""Hermes tool handlers — delegate to agent_platform.wiki WikiService (M3 D7)."""

from __future__ import annotations

import json
import logging
from typing import Any, Optional

from agent_platform.integrations.hermes.tools import (
    _tool_error,
    _tool_result,
    bootstrap_agent_platform,
)

logger = logging.getLogger(__name__)


def _session_trace_id(kwargs: dict) -> Optional[str]:
    sid = kwargs.get("current_session_id") or kwargs.get("session_id")
    if not sid:
        return None
    return f"hermes-{sid}"


def _get_wiki_service():
    bootstrap_agent_platform()
    from agent_platform.wiki.service import WikiService

    return WikiService()


def wiki_ingest(args: dict, **kwargs) -> str:
    source_path = (args.get("source_path") or "").strip()
    if not source_path:
        return _tool_error("Missing required parameter: source_path (e.g. raw/articles/note.md)")

    try:
        from agent_platform.wiki.contracts import WikiIngestRequest
        from agent_platform.wiki.ingest import WikiIngestError

        svc = _get_wiki_service()
        req_kw: dict[str, Any] = {"source_path": source_path, "topic": args.get("topic")}
        tid = args.get("trace_id") or _session_trace_id(kwargs)
        if tid:
            req_kw["trace_id"] = tid
        refs = svc.ingest(WikiIngestRequest(**req_kw))
        pages = [
            {
                "path": r.path,
                "title": r.title,
                "summary": r.summary,
                "kind": r.kind.value if r.kind else None,
            }
            for r in refs
        ]
        return _tool_result(
            {
                "success": True,
                "pages": pages,
                "count": len(pages),
                "store_root": str(svc.store_root),
                "message": "Ingested into LLM Wiki (wiki/ + index.md + log.md).",
            }
        )
    except WikiIngestError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("wiki_ingest failed")
        return _tool_error(f"Ingest failed: {e}")


def wiki_query(args: dict, **kwargs) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return _tool_error("Missing required parameter: query")

    try:
        from agent_platform.wiki.contracts import WikiQueryRequest

        svc = _get_wiki_service()
        res = svc.query(
            WikiQueryRequest(
                query=query,
                limit=int(args.get("limit", 8)),
                trace_id=args.get("trace_id") or _session_trace_id(kwargs),
            )
        )
        hits = [
            {
                "path": h.path,
                "title": h.title,
                "summary": h.summary,
                "score": h.score,
            }
            for h in res.hits
        ]
        return _tool_result(
            {
                "success": True,
                "hits": hits,
                "count": len(hits),
                "answer": res.answer,
                "raw": res.raw,
                "store_root": str(svc.store_root),
            }
        )
    except Exception as e:
        logger.exception("wiki_query failed")
        return _tool_error(f"Query failed: {e}")


def wiki_precipitate_evaluate(args: dict, **kwargs) -> str:
    """Optional D6 bridge — should Agent offer wiki ingest?"""
    session_id = (args.get("session_id") or kwargs.get("current_session_id") or "default").strip()
    message = (args.get("message") or "").strip()
    role = args.get("role") or "user"

    try:
        svc = _get_wiki_service()
        dec = svc.evaluate_precipitate_offer(
            str(session_id),
            message=message,
            role=role,
            topic=args.get("topic"),
            record=bool(args.get("record", True)),
        )
        return _tool_result(
            {
                "success": True,
                "offer": dec.offer,
                "reason_code": dec.reason_code,
                "message": dec.message,
                "topic": dec.topic,
                "assistant_turns": dec.assistant_turns,
                "user_chars": dec.user_chars,
                "details": dec.details,
            }
        )
    except Exception as e:
        logger.exception("wiki_precipitate_evaluate failed")
        return _tool_error(f"Precipitate evaluate failed: {e}")


def check_wiki_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.wiki.service import WikiService  # noqa: F401

        return True
    except Exception as e:
        logger.debug("wiki tools not available: %s", e)
        return False


WIKI_INGEST_SCHEMA: dict[str, Any] = {
    "name": "wiki_ingest",
    "description": (
        "Ingest a raw markdown file under wiki_data/raw/ into the LLM Wiki compiled layer. "
        "Creates/updates wiki/concepts/*.md, index.md, and log.md. "
        "Use for topic knowledge (US-4) — NOT for user preferences (use agent_memory_write)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "source_path": {
                "type": "string",
                "description": "Path under store raw/, e.g. raw/articles/mcp-notes.md",
            },
            "topic": {
                "type": "string",
                "description": "Page title / topic slug hint.",
            },
        },
        "required": ["source_path"],
    },
}

WIKI_QUERY_SCHEMA: dict[str, Any] = {
    "name": "wiki_query",
    "description": (
        "Search the LLM Wiki (index + compiled wiki pages). "
        "Prefer this over re-deriving topic knowledge from scratch when wiki pages exist."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Question or keywords."},
            "limit": {"type": "integer", "default": 8},
        },
        "required": ["query"],
    },
}

WIKI_PRECIPITATE_SCHEMA: dict[str, Any] = {
    "name": "wiki_precipitate_evaluate",
    "description": (
        "After a deep multi-turn discussion, check whether to offer沉淀 to the wiki. "
        "Default product mode is silent unless depth threshold or user said /沉淀."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "session_id": {"type": "string", "description": "Chat session id."},
            "message": {"type": "string", "description": "Latest user or assistant message."},
            "role": {
                "type": "string",
                "enum": ["user", "assistant", "system"],
                "default": "user",
            },
            "topic": {"type": "string"},
            "record": {
                "type": "boolean",
                "default": True,
                "description": "Record this turn in session counters.",
            },
        },
    },
}


def register_wiki_hermes_tools(ctx) -> None:
    """Register wiki tools on Hermes PluginContext."""
    ctx.register_tool(
        name="wiki_ingest",
        toolset="agent_wiki",
        schema=WIKI_INGEST_SCHEMA,
        handler=lambda args, **kw: wiki_ingest(args, **kw),
        check_fn=check_wiki_available,
        emoji="📚",
    )
    ctx.register_tool(
        name="wiki_query",
        toolset="agent_wiki",
        schema=WIKI_QUERY_SCHEMA,
        handler=lambda args, **kw: wiki_query(args, **kw),
        check_fn=check_wiki_available,
        emoji="🔍",
    )
    ctx.register_tool(
        name="wiki_precipitate_evaluate",
        toolset="agent_wiki",
        schema=WIKI_PRECIPITATE_SCHEMA,
        handler=lambda args, **kw: wiki_precipitate_evaluate(args, **kw),
        check_fn=check_wiki_available,
        emoji="💧",
    )
