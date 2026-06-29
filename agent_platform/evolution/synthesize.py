"""L2 skill synthesis — keyword clustering (Phase 1)."""

from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from agent_platform.evolution.contracts import ExperienceRecord, SkillRecord, SkillStatus


def _shared_keywords(exps: list[ExperienceRecord]) -> set[str]:
    if not exps:
        return set()
    sets = [set(e.keywords) for e in exps if e.keywords]
    if not sets:
        return set()
    shared = sets[0].copy()
    for s in sets[1:]:
        shared &= s
    return shared


def synthesize_skills(
    experiences: Iterable[ExperienceRecord],
    cfg: dict | None = None,
) -> list[SkillRecord]:
    cfg = cfg or {}
    syn = cfg.get("synthesize") or {}
    min_n = int(syn.get("min_experiences_per_skill", 3))
    min_shared = int(syn.get("min_shared_keywords", 2))
    min_conf = float(syn.get("min_confidence", 0.35))

    by_topic: dict[str, list[ExperienceRecord]] = defaultdict(list)
    for exp in experiences:
        if exp.task_success:
            by_topic[exp.topic].append(exp)

    skills: list[SkillRecord] = []
    for topic, group in by_topic.items():
        if len(group) < min_n:
            continue
        shared = _shared_keywords(group)
        if len(shared) < min_shared:
            # fallback: top frequency keywords across group
            freq: dict[str, int] = {}
            for e in group:
                for k in e.keywords:
                    freq[k] = freq.get(k, 0) + 1
            shared = {k for k, c in freq.items() if c >= 2}
        if len(shared) < min_shared:
            continue

        triggers = sorted(shared)[:5]
        name = f"{topic}_" + "_".join(list(triggers)[:2])
        procedure_parts = []
        for e in group[:3]:
            if e.successful_strategy:
                procedure_parts.append(e.successful_strategy[:120])
        procedure = " → ".join(procedure_parts) or group[0].summary

        confidence = min(0.35 + 0.05 * len(group) + 0.03 * len(shared), 0.85)
        if confidence < min_conf:
            continue

        skills.append(
            SkillRecord(
                name=name,
                description=f"从 {len(group)} 次 {topic} 对话归纳的可复用做法",
                topic=topic,
                triggers=triggers,
                procedure=procedure,
                guardrails="仅在同 topic + 相似触发词时使用；不确定时仍应查证。",
                success_criteria="用户未纠正且 task_success=true",
                confidence=confidence,
                status=SkillStatus.unverified,
                source_experience_ids=[e.experience_id for e in group],
            )
        )
    return skills


_SYNTH_LLM_SYSTEM = """You synthesize a reusable agent skill from similar successful experiences.
Return ONLY JSON with keys:
name (snake_case string), description (string), triggers (string array, 3-5),
procedure (string, step-by-step), guardrails (string), confidence (0.0-1.0)."""


def synthesize_skills_llm(
    experiences: Iterable[ExperienceRecord],
    cfg: dict | None = None,
) -> list[SkillRecord]:
    """LLM L2 synthesis for topic groups meeting min count."""
    from collections import defaultdict

    from agent_platform.evolution.llm_client import chat_json, llm_available

    if not llm_available(cfg):
        return []
    cfg = cfg or {}
    syn = cfg.get("synthesize") or {}
    min_n = int(syn.get("min_experiences_per_skill", 3))
    by_topic: dict[str, list[ExperienceRecord]] = defaultdict(list)
    for exp in experiences:
        if exp.task_success:
            by_topic[exp.topic].append(exp)

    skills: list[SkillRecord] = []
    for topic, group in by_topic.items():
        if len(group) < min_n:
            continue
        blob = "\n".join(f"- {e.summary}" for e in group[:6])
        data = chat_json(
            _SYNTH_LLM_SYSTEM,
            f"Topic: {topic}\nExperiences:\n{blob}",
            cfg,
        )
        if not data:
            continue
        triggers = data.get("triggers") or []
        if isinstance(triggers, str):
            triggers = [triggers]
        skills.append(
            SkillRecord(
                name=str(data.get("name") or f"{topic}_skill")[:60],
                description=str(data.get("description") or f"LLM skill for {topic}")[:300],
                topic=topic,
                triggers=[str(t)[:40] for t in triggers][:5],
                procedure=str(data.get("procedure") or blob)[:800],
                guardrails=str(data.get("guardrails") or "Verify before reuse."),
                success_criteria="User did not correct; task_success=true",
                confidence=float(data.get("confidence") or 0.55),
                status=SkillStatus.unverified,
                source_experience_ids=[e.experience_id for e in group],
                metadata={"synthesizer": "llm"},
            )
        )
    return skills


def synthesize_skills_from_experiences(
    experiences: Iterable[ExperienceRecord],
    cfg: dict | None = None,
) -> list[SkillRecord]:
    """Phase 3 entry: rules | llm | auto."""
    cfg = cfg or {}
    mode = str((cfg.get("phase3") or {}).get("synthesize_mode", "rules")).lower()
    rule_skills = synthesize_skills(experiences, cfg)
    if mode == "rules":
        return rule_skills
    if mode in ("llm", "auto"):
        llm_skills = synthesize_skills_llm(experiences, cfg)
        if llm_skills:
            return llm_skills
    return rule_skills
