"""Dismiss feedback → memory_service with dedup (M5 D2 / US-5)."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Optional

from agent_platform.memory.contracts import MemoryCategory, MemoryKind

logger = logging.getLogger(__name__)

DISMISS_SUBJECT_KEY = "proactive.do_not_disturb"
DEFAULT_DEDUP_QUERY = "不希望主动提醒 别打扰"


@dataclass
class DismissMemoryResult:
    written: bool
    deduped: bool = False
    record_id: Optional[str] = None
    error: Optional[str] = None
    content: str = ""


def build_dismiss_content(
    *,
    template: str,
    user_message: str,
    session_id: str,
) -> str:
    msg = (user_message or "").strip()
    base = (template or "").strip()
    if msg and msg not in base:
        return f"{base} 用户原话：「{msg[:200]}」"
    return base or f"用户不希望主动打扰（session={session_id}）"


def _existing_dismiss_hit(memory_service: Any, *, device_id: str, query: str) -> bool:
    try:
        from agent_platform.memory.contracts import MemoryCategory

        probes = ["别打扰", "主动提醒", "do not disturb"]
        if query:
            probes.insert(0, query.split()[0] if query.split() else query)

        seen: set[str] = set()
        for q in probes:
            q = q.strip().lower()
            if not q or q in seen:
                continue
            seen.add(q)
            res = memory_service.search(
                q,
                device_id=device_id,
                category=MemoryCategory.preference,
                limit=8,
            )
            for h in res.hits or []:
                meta = getattr(h, "metadata", None) or {}
                if meta.get("subject_key") == DISMISS_SUBJECT_KEY:
                    return True
                text = (getattr(h, "content", None) or "").lower()
                if "主动提醒" in text or "别打扰" in text or "do not disturb" in text:
                    return True
    except Exception as e:
        logger.debug("dismiss dedup search skipped: %s", e)
    return False


def write_dismiss_preference(
    memory_service: Any,
    *,
    content: str,
    device_id: str,
    trace_id: str,
    category: str = "preference",
    dedup_enabled: bool = True,
    dedup_query: str = DEFAULT_DEDUP_QUERY,
) -> DismissMemoryResult:
    """Write US-5 dismiss preference; skip if similar preference already exists."""
    if dedup_enabled and _existing_dismiss_hit(memory_service, device_id=device_id, query=dedup_query):
        return DismissMemoryResult(
            written=False,
            deduped=True,
            content=content,
            error=None,
        )

    try:
        rec = memory_service.write(
            content,
            device_id=device_id,
            category=MemoryCategory(category),
            kind=MemoryKind.preference,
            trace_id=trace_id,
            subject_key=DISMISS_SUBJECT_KEY,
            metadata={
                "subject_key": DISMISS_SUBJECT_KEY,
                "source": "proactive_feedback",
                "us5": True,
            },
        )
        return DismissMemoryResult(
            written=True,
            deduped=False,
            record_id=getattr(rec, "record_id", None),
            content=content,
        )
    except Exception as e:
        logger.exception("write_dismiss_preference failed")
        return DismissMemoryResult(
            written=False,
            deduped=False,
            error=str(e),
            content=content,
        )
