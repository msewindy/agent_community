"""L1 experience extraction — rule-based (Phase 1, no LLM required)."""

from __future__ import annotations

import re
from typing import Any

from agent_platform.evolution.contracts import ExperienceComplexity, ExperienceRecord

_FAIL_MARKERS = (
    "error", "sorry", "cannot", "unable",
    "抱歉", "无法", "做不到", "不支持", "出错",
)
_TOPIC_HINTS: list[tuple[str, list[str]]] = [
    ("memory", ["记忆", "记住", "偏好", "memory", "remember"]),
    ("tools", ["工具", "mcp", "fetch", "文件", "tool"]),
    ("wiki", ["wiki", "知识", "沉淀", "文档"]),
    ("workflow", ["流程", "步骤", "周报", "导出", "workflow"]),
]


def _keywords(text: str, limit: int = 8) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower())
    freq: dict[str, int] = {}
    for t in tokens:
        if t in {"the", "and", "this", "that", "一个", "我们", "可以"}:
            continue
        freq[t] = freq.get(t, 0) + 1
    ranked = sorted(freq.items(), key=lambda x: (-x[1], x[0]))
    return [w for w, _ in ranked[:limit]]


def _complexity(user: str, assistant: str) -> ExperienceComplexity:
    n = len(user.strip()) + len(assistant.strip())
    if n < 40:
        return ExperienceComplexity.trivial
    if n < 200:
        return ExperienceComplexity.moderate
    return ExperienceComplexity.complex


def _infer_topic(keywords: list[str], user: str) -> str:
    blob = " ".join(keywords) + " " + user.lower()
    for topic, hints in _TOPIC_HINTS:
        if any(h in blob for h in hints):
            return topic
    return "general"


def _summary(user: str, assistant: str) -> str:
    u = user.strip().replace("\n", " ")[:80]
    a = assistant.strip().replace("\n", " ")[:120]
    return f"用户: {u} | 助手: {a}"


def extract_experience(user_msg: str, assistant_msg: str, cfg: dict | None = None) -> ExperienceRecord | None:
    """Return None when quality gates reject the turn."""
    cfg = cfg or {}
    ext = cfg.get("extract") or {}
    min_u = int(ext.get("min_user_chars", 8))
    min_a = int(ext.get("min_assistant_chars", 12))
    skip_trivial = bool(ext.get("skip_complexity", True))
    blacklist = {str(x).lower() for x in (ext.get("blacklist_topics") or [])}

    user_msg = user_msg or ""
    assistant_msg = assistant_msg or ""
    if len(user_msg.strip()) < min_u or len(assistant_msg.strip()) < min_a:
        return None

    complexity = _complexity(user_msg, assistant_msg)
    if skip_trivial and complexity == ExperienceComplexity.trivial:
        return None

    kws = _keywords(f"{user_msg}\n{assistant_msg}")
    topic = _infer_topic(kws, user_msg)
    if topic.lower() in blacklist:
        return None

    task_success = not any(m in assistant_msg.lower() for m in _FAIL_MARKERS)
    strategy = None
    if task_success and len(assistant_msg) > 40:
        strategy = assistant_msg.strip()[:200]

    return ExperienceRecord(
        user_message=user_msg,
        assistant_message=assistant_msg,
        summary=_summary(user_msg, assistant_msg),
        topic=topic,
        keywords=kws,
        task_success=task_success,
        complexity=complexity,
        user_intent=user_msg.strip()[:200],
        successful_strategy=strategy,
    )


_EXTRACT_LLM_SYSTEM = """You extract structured learning signals from one agent turn.
Return ONLY JSON with keys:
summary (string), topic (string), keywords (string array, max 8),
task_success (boolean), successful_strategy (string or null, concise how-to)."""


def extract_experience_llm(user_msg: str, assistant_msg: str, cfg: dict | None = None) -> ExperienceRecord | None:
    """LLM-enriched L1; returns None if gates fail or LLM unavailable."""
    base = extract_experience(user_msg, assistant_msg, cfg)
    if base is None:
        return None
    from agent_platform.evolution.llm_client import chat_json, llm_available

    if not llm_available(cfg):
        return base
    data = chat_json(
        _EXTRACT_LLM_SYSTEM,
        f"USER:\n{user_msg}\n\nASSISTANT:\n{assistant_msg}",
        cfg,
    )
    if not data:
        return base
    topic = str(data.get("topic") or base.topic)[:40]
    kws = data.get("keywords") or base.keywords
    if isinstance(kws, str):
        kws = [kws]
    kws = [str(k)[:40] for k in kws][:8]
    return base.model_copy(
        update={
            "summary": str(data.get("summary") or base.summary)[:300],
            "topic": topic,
            "keywords": kws or base.keywords,
            "task_success": bool(data.get("task_success", base.task_success)),
            "successful_strategy": data.get("successful_strategy") or base.successful_strategy,
            "metadata": {**base.metadata, "extractor": "llm"},
        }
    )


def extract_experience_from_turn(user_msg: str, assistant_msg: str, cfg: dict | None = None) -> ExperienceRecord | None:
    """Phase 3 entry: rules | llm | auto."""
    cfg = cfg or {}
    mode = str((cfg.get("phase3") or {}).get("extract_mode", "rules")).lower()
    if mode == "llm":
        return extract_experience_llm(user_msg, assistant_msg, cfg) or extract_experience(user_msg, assistant_msg, cfg)
    if mode == "auto":
        from agent_platform.evolution.llm_client import llm_available

        if llm_available(cfg):
            llm_exp = extract_experience_llm(user_msg, assistant_msg, cfg)
            if llm_exp:
                return llm_exp
    return extract_experience(user_msg, assistant_msg, cfg)
