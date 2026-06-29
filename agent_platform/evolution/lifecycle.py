"""L3 skill lifecycle — promote, demote, deprecate (Phase 3)."""

from __future__ import annotations

import re
from typing import Iterable

from agent_platform.evolution.contracts import SkillRecord, SkillStatus


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[\w\u4e00-\u9fff]{2,}", (text or "").lower()))


def record_skill_usage(skill: SkillRecord, cfg: dict | None = None) -> SkillRecord:
    """Increment usage; promote unverified → active after threshold."""
    cfg = cfg or {}
    lc = cfg.get("lifecycle") or {}
    threshold = int(lc.get("promote_after_uses", 3))
    skill.usage_count += 1
    if skill.status == SkillStatus.unverified and skill.usage_count >= threshold:
        skill.status = SkillStatus.active
        skill.confidence = min(skill.confidence + 0.05, 0.9)
    return skill


def skills_matching_correction(
    skills: Iterable[SkillRecord],
    user_message: str,
    correction_note: str,
) -> list[SkillRecord]:
    """Find skills whose triggers/procedure overlap correction text."""
    blob = f"{user_message} {correction_note}".lower()
    tokens = _tokenize(blob)
    hits: list[SkillRecord] = []
    for skill in skills:
        if skill.status == SkillStatus.deprecated:
            continue
        skill_tokens = _tokenize(" ".join(skill.triggers) + " " + skill.procedure + " " + skill.topic)
        overlap = tokens & skill_tokens
        trigger_hit = any(t.lower() in blob for t in skill.triggers)
        if len(overlap) >= 2 or skill.topic.lower() in blob or trigger_hit:
            hits.append(skill)
    return hits


def apply_correction_to_skills(
    skills: list[SkillRecord],
    user_message: str,
    correction_note: str,
    cfg: dict | None = None,
) -> list[SkillRecord]:
    """L5: demote or deprecate skills implicated by user correction."""
    cfg = cfg or {}
    lc = cfg.get("lifecycle") or {}
    demote = float(lc.get("demote_on_correction", 0.15))
    deprecate = bool(lc.get("deprecate_on_correction", True))
    updated: list[SkillRecord] = []
    for skill in skills_matching_correction(skills, user_message, correction_note):
        skill.confidence = max(0.05, skill.confidence - demote)
        note = f"用户纠正: {user_message[:60]}"
        skill.guardrails = (skill.guardrails or "") + f"\n- {note}: {correction_note[:120]}"
        if deprecate and skill.confidence < 0.25:
            skill.status = SkillStatus.deprecated
        updated.append(skill)
    return updated


def filter_recallable_skills(skills: Iterable[SkillRecord]) -> list[SkillRecord]:
    return [s for s in skills if s.status != SkillStatus.deprecated]
