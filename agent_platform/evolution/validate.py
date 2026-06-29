"""L5 validation — correction detection + skill guardrails (Phase 3)."""

from __future__ import annotations

from typing import Iterable

from agent_platform.evolution.contracts import ExperienceRecord, SkillRecord


def looks_like_user_correction(user_message: str, cfg: dict | None = None) -> bool:
    cfg = cfg or {}
    l5 = cfg.get("l5") or {}
    keywords = l5.get("correction_keywords") or [
        "不对", "错了", "纠正", "记错", "应该用", "不是", "别用", "更正",
        "incorrect", "wrong", "correction", "fix that",
    ]
    text = (user_message or "").lower()
    return any(k.lower() in text for k in keywords)


def build_correction_experience(
    user_message: str,
    note: str,
    *,
    linked_skill_ids: list[str] | None = None,
) -> ExperienceRecord:
    meta = {"kind": "user_correction", "phase": 3}
    if linked_skill_ids:
        meta["linked_skill_ids"] = linked_skill_ids
    return ExperienceRecord(
        user_message=user_message,
        assistant_message=note,
        summary=f"用户纠正: {user_message[:80]}",
        topic="correction",
        keywords=["correction", "guardrail"],
        task_success=False,
        failure_recovery=note,
        metadata=meta,
    )


def validate_skill_for_recall(skill: SkillRecord, query: str) -> bool:
    """Drop skills whose guardrails explicitly warn against query terms."""
    if not skill.guardrails:
        return True
    q = query.lower()
    for line in skill.guardrails.splitlines():
        if "用户纠正" in line and any(tok in line.lower() for tok in q.split() if len(tok) >= 2):
            return False
    return True


def filter_validated_skills(skills: Iterable[SkillRecord], query: str) -> list[SkillRecord]:
    return [s for s in skills if validate_skill_for_recall(s, query)]
