"""L0 — assess whether basic user profile (C-PROFILE) is warm enough for scene use."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from agent_platform.learning.student_identity import _extract_name_from_text
from agent_platform.memory.contracts import MemoryCategory

_INTEREST_PATTERN = re.compile(
    r"喜欢|爱好|兴趣|爱(玩|打|看|画|听|踢|跳)|擅长|经常(玩|看)"
)
_GRADE_PATTERN = re.compile(r"([一二三四五六])年级|上?(\d)年级")
_DIGIT_TO_CN = {"1": "一", "2": "二", "3": "三", "4": "四", "5": "五", "6": "六"}
_INTEREST_EXTRACT = re.compile(r"喜欢([^。，,！!？?]{2,40})")
_STYLE_ONLY = re.compile(
    r"回复|简短|详细|语气|风格|直接|啰嗦|别催|打扰"
)


@dataclass
class ProfileSnapshot:
    has_display_name: bool = False
    has_grade_hint: bool = False
    has_interest: bool = False
    display_name: Optional[str] = None
    grade_label: Optional[str] = None
    missing: list[str] = field(default_factory=list)

    @property
    def is_complete(self) -> bool:
        return self.has_display_name and self.has_grade_hint and self.has_interest

    @property
    def needs_onboarding(self) -> bool:
        return not self.is_complete


def extract_grade_label_from_text(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    m = _GRADE_PATTERN.search(text)
    if not m:
        return None
    if m.group(1):
        return f"{m.group(1)}年级"
    digit = (m.group(2) or "").strip()
    cn = _DIGIT_TO_CN.get(digit)
    return f"{cn}年级" if cn else None


def extract_interest_phrase_from_text(text: str) -> Optional[str]:
    if not text or not text.strip():
        return None
    m = _INTEREST_EXTRACT.search(text)
    if m:
        phrase = m.group(1).strip()
        if len(phrase) >= 2:
            return phrase
    if _INTEREST_PATTERN.search(text):
        return text.strip()[:80]
    return None


def _scan_records_for_name(records) -> Optional[str]:
    for rec in records:
        if getattr(rec, "status", None) and str(rec.status) == "tombstoned":
            continue
        name = _extract_name_from_text(rec.content)
        if name:
            return name
    return None


def _scan_records_for_interest(records) -> bool:
    for rec in records:
        if getattr(rec, "status", None) and str(rec.status) == "tombstoned":
            continue
        text = (rec.content or "").strip()
        if not text or _STYLE_ONLY.search(text):
            continue
        if _INTEREST_PATTERN.search(text):
            return True
        cat = getattr(rec, "category", None)
        if cat == MemoryCategory.preference and len(text) >= 4:
            return True
    return False


def assess_profile(
    *,
    memory_svc=None,
    device_id: Optional[str] = None,
    onboarding_grade: Optional[str] = None,
    context_grade: Optional[str] = None,
    onboarding_preferred_name: Optional[str] = None,
) -> ProfileSnapshot:
    """Read-only profile warmth check (M2 + optional L1 onboarding hints)."""
    snap = ProfileSnapshot()
    name = (onboarding_preferred_name or "").strip() or None
    grade = (onboarding_grade or context_grade or "").strip() or None
    if grade:
        snap.has_grade_hint = True
        snap.grade_label = grade

    try:
        if memory_svc is None:
            from agent_platform.memory.service import MemoryService

            memory_svc = MemoryService()
        did = device_id or memory_svc.default_device_id
        collected: list = []
        for category in (MemoryCategory.user_profile, MemoryCategory.preference, None):
            kwargs = {"device_id": did, "limit": 300}
            if category is not None:
                kwargs["category"] = category
            collected.extend(memory_svc.list_records(**kwargs))

        if not name:
            name = _scan_records_for_name(collected)
        if not snap.has_grade_hint:
            for rec in collected:
                text = rec.content or ""
                gl = extract_grade_label_from_text(text)
                if gl:
                    snap.has_grade_hint = True
                    snap.grade_label = gl
                    break
                if re.search(r"[一二三四五六]年级|grade", text, re.I):
                    snap.has_grade_hint = True
                    m = re.search(r"([一二三四五六])年级", text)
                    if m:
                        snap.grade_label = f"{m.group(1)}年级"
                    break

        snap.has_interest = _scan_records_for_interest(collected)
    except Exception:
        pass

    if name:
        snap.has_display_name = True
        snap.display_name = name

    missing: list[str] = []
    if not snap.has_display_name:
        missing.append("name")
    if not snap.has_grade_hint:
        missing.append("grade")
    if not snap.has_interest:
        missing.append("interest")
    snap.missing = missing
    return snap
