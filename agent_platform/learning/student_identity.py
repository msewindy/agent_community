"""Resolve student display name from M2 user_profile (Agent track)."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Optional

from agent_platform.learning._config import load_student_learning_config, resolve_data_root
from agent_platform.learning.contracts import StudentContext
from agent_platform.learning.store import layout_for
from agent_platform.memory.contracts import MemoryCategory

_NAME_PATTERNS = (
    re.compile(r"姓名[是为：:\s]+([^\s，,。/]{2,4})"),
    re.compile(r"名字[是为叫：:\s]+([^\s，,。/]{2,4})"),
    re.compile(r"叫[「『]?([^，。,\s」』]{2,4})"),
    re.compile(r"孩子[是为叫：:\s]+([^\s，,。/]{2,4})"),
    re.compile(r"我是([^\s，,。/！!？?]{2,4})"),
    re.compile(r"可以叫我([^\s，,。/！!？?]{2,4})"),
    re.compile(r"叫我([^\s，,。/！!？?]{2,4})"),
    re.compile(r"称呼我[为]?([^\s，,。/！!？?]{2,4})"),
    re.compile(r"([^\s，,。/]{2,4})[/／]\d+岁"),
    re.compile(r"刘([^\s，,。/]{2,3})[/／]"),
    re.compile(r"是([^\s，,。/]{2,3})[/／]"),
)

_SKIP_NAMES = frozenset(
    {
        "学生",
        "孩子",
        "小朋友",
        "二年级",
        "三年级",
        "四年级",
        "五年级",
        "六年级",
        "数学",
        "语文",
        "英语",
        "Jarvis",
        "小贾",
        "喜欢",
        "今年",
    }
)


def _extract_name_from_text(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    for pat in _NAME_PATTERNS:
        m = pat.search(text)
        if not m:
            continue
        name = m.group(1).strip()
        if 2 <= len(name) <= 4 and name not in _SKIP_NAMES:
            return name
    return None


def _memory_device_for_student(student_id: str, cfg: dict) -> Optional[str]:
    profiles = (cfg.get("students") or {}).get("profiles") or {}
    entry = profiles.get(student_id) or {}
    raw = (entry.get("memory_device_id") or "").strip()
    return raw or None


def _config_preferred_name(student_id: str, cfg: dict) -> Optional[str]:
    profiles = (cfg.get("students") or {}).get("profiles") or {}
    entry = profiles.get(student_id) or {}
    name = (entry.get("preferred_name") or "").strip()
    return name or None


def _onboarding_preferred_name(student_id: str, data_root: Optional[Path]) -> Optional[str]:
    try:
        lay = layout_for(student_id, data_root)
        if not lay.profile_path.is_file():
            return None
        import json

        raw = json.loads(lay.profile_path.read_text(encoding="utf-8"))
        name = (raw.get("preferred_name") or "").strip()
        return name or None
    except Exception:
        return None


def memory_device_for_student(student_id: str, cfg: dict) -> Optional[str]:
    return _memory_device_for_student(student_id, cfg)


def resolve_student_friendly_name(
    student_id: str,
    cfg: dict,
    *,
    ctx: Optional[StudentContext] = None,
    memory_svc=None,
    data_root: Optional[Path] = None,
) -> Optional[str]:
    """Return display name if known; None if only student_id is available."""
    resolved = resolve_student_display_name(
        student_id,
        cfg,
        ctx=ctx,
        memory_svc=memory_svc,
        data_root=data_root,
    )
    if resolved and resolved != student_id:
        return resolved
    return None


def student_list_label(
    student_id: str,
    cfg: dict,
    *,
    grade: str = "",
    ctx: Optional[StudentContext] = None,
    memory_svc=None,
    data_root: Optional[Path] = None,
) -> str:
    """Parent-panel list label: prefer nickname, never show raw id as the only label."""
    name = resolve_student_friendly_name(
        student_id,
        cfg,
        ctx=ctx,
        memory_svc=memory_svc,
        data_root=data_root,
    )
    label = name or "未设置昵称"
    if grade:
        return f"{label}（{grade}）"
    return label


def resolve_student_display_name(
    student_id: str,
    cfg: dict,
    *,
    ctx: Optional[StudentContext] = None,
    memory_svc=None,
    data_root: Optional[Path] = None,
) -> str:
    """Prefer M2 user_profile; then onboarding/config preferred_name; last student_id."""
    root = data_root or resolve_data_root(cfg)
    device_id = _memory_device_for_student(student_id, cfg)
    try:
        if memory_svc is None:
            from agent_platform.memory.service import MemoryService

            memory_svc = MemoryService()
        did = device_id or memory_svc.default_device_id
        for category in (MemoryCategory.user_profile, MemoryCategory.preference, None):
            kwargs = {"device_id": did, "limit": 300}
            if category is not None:
                kwargs["category"] = category
            records = memory_svc.list_records(**kwargs)
            for rec in records:
                name = _extract_name_from_text(rec.content)
                if name:
                    return name
        for query in ("盈熙", "孩子姓名", "学生名字", "叫什么", "刘盈熙", student_id):
            result = memory_svc.search(query, device_id=did, limit=12)
            for hit in result.hits:
                name = _extract_name_from_text(hit.content)
                if name:
                    return name
    except Exception:
        pass

    onboard_name = _onboarding_preferred_name(student_id, root)
    if onboard_name:
        return onboard_name

    config_name = _config_preferred_name(student_id, cfg)
    if config_name:
        return config_name

    if ctx and ctx.goal and ctx.goal.label:
        label = ctx.goal.label.strip()
        if label and label not in _SKIP_NAMES and len(label) <= 8:
            return label
    return student_id
