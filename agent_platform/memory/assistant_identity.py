"""L0 — assistant display name (default 贾维斯 + user alias from M2)."""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.memory.contracts import MemoryCategory

DEFAULT_ASSISTANT_NAME = "贾维斯"
ASSISTANT_ALIAS_SUBJECT_KEY = "assistant_alias"

_ALIAS_PATTERNS = (
    re.compile(r"助手别名[是为：:\s]+([^\s，,。！!？?]{1,8})"),
    re.compile(r"以后叫你[叫]?([^\s，,。！!？?]{1,8})"),
    re.compile(r"我叫你([^\s，,。！!？?]{1,8})"),
    re.compile(r"叫你([^\s，,。！!？?]{1,8})"),
    re.compile(r"你的(名字|昵称)[是为叫：:\s]+([^\s，,。！!？?]{1,8})"),
)

_SKIP_ALIAS = frozenset(
    {
        "贾维斯",
        "Jarvis",
        "jarvis",
        "小贾",
        "同学",
        "老师",
        "助手",
        "学习助手",
        "学习小助手",
        "我",
        "你",
        "什么",
    }
)


def _clean_alias(raw: str) -> Optional[str]:
    name = (raw or "").strip().strip("「」『』\"'")
    if not name or len(name) > 8:
        return None
    if name in _SKIP_ALIAS:
        return None
    return name


def _extract_alias_from_text(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    for pat in _ALIAS_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        candidate = m.group(m.lastindex or 1)
        cleaned = _clean_alias(candidate)
        if cleaned:
            return cleaned
    return None


def resolve_assistant_display_name(
    *,
    memory_svc=None,
    device_id: Optional[str] = None,
    cfg: Optional[dict] = None,
) -> str:
    """User alias from M2 → config default → 贾维斯."""
    default = DEFAULT_ASSISTANT_NAME
    if cfg:
        raw = (cfg.get("hermes") or {}).get("default_assistant_name")
        if isinstance(raw, str) and raw.strip():
            default = raw.strip()

    try:
        if memory_svc is None:
            from agent_platform.memory.service import MemoryService

            memory_svc = MemoryService(cfg)
        did = device_id or memory_svc.default_device_id
        for category in (MemoryCategory.preference, MemoryCategory.user_profile, None):
            kwargs = {"device_id": did, "limit": 300}
            if category is not None:
                kwargs["category"] = category
            for rec in memory_svc.list_records(**kwargs):
                if getattr(rec, "status", None) and str(rec.status) == "tombstoned":
                    continue
                meta = rec.metadata or {}
                if meta.get("subject_key") == ASSISTANT_ALIAS_SUBJECT_KEY:
                    from_content = _extract_alias_from_text(rec.content) or _clean_alias(
                        rec.content.replace("助手别名", "").strip(" ：:")
                    )
                    if from_content:
                        return from_content
                alias = _extract_alias_from_text(rec.content)
                if alias:
                    return alias
    except Exception:
        pass
    return default


def assistant_alias_memory_content(alias: str) -> str:
    """Canonical M2 content when persisting a user-chosen assistant alias."""
    return f"助手别名：{alias.strip()}"
