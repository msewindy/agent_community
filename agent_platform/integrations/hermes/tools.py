"""Hermes tool handlers — delegate to agent_platform.memory_service (M2 D8)."""

from __future__ import annotations

import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Optional

logger = logging.getLogger(__name__)

_REPO_ROOT = Path(__file__).resolve().parents[3]


def bootstrap_agent_platform() -> Path:
    """Ensure repo root is on sys.path for Hermes plugin loads."""
    root = os.environ.get("AGENT_COMMUNITY_ROOT", "").strip()
    if not root:
        marker = Path(__file__).resolve().parent / "agent_memverse" / "AGENT_COMMUNITY_ROOT"
        if marker.is_file():
            root = marker.read_text(encoding="utf-8").strip()
    if not root:
        root = str(_REPO_ROOT)
    root_path = Path(root)
    s = str(root_path)
    if s not in sys.path:
        sys.path.insert(0, s)
    return root_path


def _get_service():
    bootstrap_agent_platform()
    from agent_platform.memory.service import get_memory_service

    return get_memory_service()


def _session_trace_id(kwargs: dict) -> Optional[str]:
    sid = kwargs.get("current_session_id") or kwargs.get("session_id")
    if not sid:
        return None
    from agent_platform.memory.trace import trace_from_session

    return trace_from_session(str(sid))


def _tool_result(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _tool_error(message: str) -> str:
    try:
        from tools.registry import tool_error

        return tool_error(message, success=False)
    except ImportError:
        return json.dumps({"error": message, "success": False}, ensure_ascii=False)


def agent_memory_write(args: dict, **kwargs) -> str:
    content = (args.get("content") or "").strip()
    if not content:
        return _tool_error("Missing required parameter: content")

    category = args.get("category") or "preference"
    kind = args.get("kind") or "preference"
    subject_key = args.get("subject_key")
    device_id = args.get("device_id")
    if not device_id:
        try:
            bootstrap_agent_platform()
            from agent_platform.learning._config import load_student_learning_config, resolve_student_id
            from agent_platform.learning.student_identity import memory_device_for_student

            sid = resolve_student_id(args=args, kwargs=kwargs)
            if sid:
                device_id = memory_device_for_student(sid, load_student_learning_config())
        except Exception:
            device_id = None

    try:
        from agent_platform.memory.contracts import MemoryCategory, MemoryKind

        svc = _get_service()
        rec = svc.write(
            content,
            device_id=device_id,
            category=MemoryCategory(category),
            kind=MemoryKind(kind),
            subject_key=subject_key,
            trace_id=args.get("trace_id") or _session_trace_id(kwargs),
        )
        return _tool_result(
            {
                "success": True,
                "record_id": rec.record_id,
                "trace_id": rec.trace_id,
                "content_hash": rec.content_hash,
                "message": "Stored in MemVerse-backed memory (via memory_service).",
            }
        )
    except PermissionError as e:
        return _tool_error(str(e))
    except Exception as e:
        logger.exception("agent_memory_write failed")
        return _tool_error(f"Write failed: {e}")


def agent_memory_search(args: dict, **kwargs) -> str:
    query = (args.get("query") or "").strip()
    if not query:
        return _tool_error("Missing required parameter: query")

    try:
        from agent_platform.memory.contracts import MemoryCategory

        svc = _get_service()
        cat = args.get("category")
        category = MemoryCategory(cat) if cat else None
        res = svc.search(
            query,
            device_id=args.get("device_id"),
            category=category,
            limit=int(args.get("limit", 8)),
            trace_id=args.get("trace_id") or _session_trace_id(kwargs),
        )
        hits = [
            {
                "record_id": h.record_id,
                "content": h.content,
                "score": h.score,
                "device_id": h.device_id,
                "category": h.category.value if h.category else None,
            }
            for h in res.hits
        ]
        payload: dict = {"success": True, "hits": hits, "count": len(hits)}
        if not hits:
            payload["message"] = (
                "No active memory records matched. Do not infer user preferences from "
                "behavior profile (M7 它的设定) or chat history — report that long-term memory has no hit."
            )
        return _tool_result(payload)
    except Exception as e:
        logger.exception("agent_memory_search failed")
        return _tool_error(f"Search failed: {e}")


def agent_memory_delete(args: dict, **kwargs) -> str:
    record_id = (args.get("record_id") or "").strip()
    if not record_id:
        return _tool_error("Missing required parameter: record_id")

    try:
        svc = _get_service()
        tomb = svc.delete(
            record_id,
            reason=args.get("reason") or "hermes_tool_delete",
            trace_id=args.get("trace_id") or _session_trace_id(kwargs),
        )
        return _tool_result(
            {
                "success": True,
                "record_id": tomb.record_id,
                "status": tomb.status.value,
                "message": "Memory tombstoned (US-7).",
            }
        )
    except KeyError:
        return _tool_error(f"Record not found: {record_id}")
    except Exception as e:
        logger.exception("agent_memory_delete failed")
        return _tool_error(f"Delete failed: {e}")


def check_agent_memory_available() -> bool:
    try:
        bootstrap_agent_platform()
        from agent_platform.memory.service import MemoryService  # noqa: F401

        return True
    except Exception as e:
        logger.debug("agent_memory not available: %s", e)
        return False


AGENT_MEMORY_WRITE_SCHEMA = {
    "name": "agent_memory_write",
    "description": (
        "Write a durable user fact or preference to the agent community memory layer (MemVerse via memory_service). "
        "Use for cross-session preferences and project facts — NOT for Hermes MEMORY.md scratch notes. "
        "Examples: reply style, timezone, project milestones. Respects product gate (dedup/conflict)."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "content": {"type": "string", "description": "Fact or preference to remember."},
            "category": {
                "type": "string",
                "enum": ["preference", "user_profile", "project", "episode", "other"],
                "default": "preference",
            },
            "kind": {
                "type": "string",
                "enum": ["fact", "preference", "episode", "note"],
                "default": "preference",
            },
            "subject_key": {
                "type": "string",
                "description": "Optional stable key for conflict detection (e.g. user.reply_style).",
            },
            "device_id": {"type": "string", "description": "Optional device scope."},
        },
        "required": ["content"],
    },
}

AGENT_MEMORY_SEARCH_SCHEMA = {
    "name": "agent_memory_search",
    "description": (
        "Search long-term user memory (M2 / memory_service). "
        "If count=0, tell the user no matching preference was stored — do NOT substitute "
        "M7 behavior profile rules (它的设定) or prior chat turns. "
        "Distinct from Hermes built-in memory tool."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query."},
            "category": {
                "type": "string",
                "enum": ["preference", "user_profile", "project", "episode", "other"],
            },
            "limit": {"type": "integer", "default": 8},
            "device_id": {"type": "string"},
        },
        "required": ["query"],
    },
}

AGENT_MEMORY_DELETE_SCHEMA = {
    "name": "agent_memory_delete",
    "description": (
        "Delete (tombstone) a memory record by record_id — data sovereignty / US-7. "
        "Obtain record_id from agent_memory_search or the memory panel."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "record_id": {"type": "string"},
            "reason": {"type": "string", "default": "user_requested_delete"},
        },
        "required": ["record_id"],
    },
}


def register_hermes_tools(ctx) -> None:
    """Register tools on Hermes PluginContext."""
    ctx.register_tool(
        name="agent_memory_write",
        toolset="agent_memory",
        schema=AGENT_MEMORY_WRITE_SCHEMA,
        handler=lambda args, **kw: agent_memory_write(args, **kw),
        check_fn=check_agent_memory_available,
        emoji="🧠",
    )
    ctx.register_tool(
        name="agent_memory_search",
        toolset="agent_memory",
        schema=AGENT_MEMORY_SEARCH_SCHEMA,
        handler=lambda args, **kw: agent_memory_search(args, **kw),
        check_fn=check_agent_memory_available,
        emoji="🔎",
    )
    ctx.register_tool(
        name="agent_memory_delete",
        toolset="agent_memory",
        schema=AGENT_MEMORY_DELETE_SCHEMA,
        handler=lambda args, **kw: agent_memory_delete(args, **kw),
        check_fn=check_agent_memory_available,
        emoji="🗑️",
    )
