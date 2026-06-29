"""Phase 4 — Voyager-style curriculum: suggest next workflows to practice."""

from __future__ import annotations

from collections import Counter, defaultdict

from agent_platform.evolution.contracts import (
    CurriculumItem,
    CurriculumKind,
    CurriculumPlan,
    ExperienceRecord,
    SkillRecord,
    SkillStatus,
)


def _topic_stats(
    experiences: list[ExperienceRecord],
    skills: list[SkillRecord],
) -> dict[str, dict]:
    stats: dict[str, dict] = defaultdict(
        lambda: {
            "success": 0,
            "failure": 0,
            "corrections": 0,
            "keywords": Counter(),
            "skills": [],
        }
    )
    for exp in experiences:
        if exp.topic in ("correction", "general", "闲聊"):
            if exp.topic == "correction" or exp.metadata.get("kind") == "user_correction":
                stats["correction"]["corrections"] += 1
            continue
        bucket = stats[exp.topic]
        if exp.task_success:
            bucket["success"] += 1
        else:
            bucket["failure"] += 1
        for k in exp.keywords:
            bucket["keywords"][k] += 1
    for skill in skills:
        if skill.status == SkillStatus.deprecated:
            continue
        stats[skill.topic]["skills"].append(skill)
    return stats


def propose_curriculum_rules(
    experiences: list[ExperienceRecord],
    skills: list[SkillRecord],
    cfg: dict | None = None,
) -> CurriculumPlan:
    """Rule-based next-practice suggestions from L1/L2 state."""
    cfg = cfg or {}
    p4 = cfg.get("phase4") or {}
    syn = cfg.get("synthesize") or {}
    min_skill_n = int(syn.get("min_experiences_per_skill", 3))
    min_gap = int(p4.get("min_experiences_for_gap", 2))
    max_items = int(p4.get("max_suggestions", 3))
    skip_topics = {str(t).lower() for t in (p4.get("skip_topics") or ["general", "correction", "闲聊"])}

    stats = _topic_stats(experiences, skills)
    items: list[CurriculumItem] = []

    for topic, data in stats.items():
        if topic.lower() in skip_topics:
            continue
        success = data["success"]
        topic_skills: list[SkillRecord] = data["skills"]
        top_kw = [k for k, _ in data["keywords"].most_common(3)]
        kw_hint = "、".join(top_kw) if top_kw else topic

        if success >= min_gap and success < min_skill_n and not topic_skills:
            need = min_skill_n - success
            items.append(
                CurriculumItem(
                    kind=CurriculumKind.gap,
                    topic=topic,
                    title=f"补齐 {topic} 经验以合成 skill",
                    rationale=f"已有 {success} 次成功对话，还差约 {need} 次可触发 L2 合成。",
                    suggested_prompt=f"请再帮我完成一次与「{kw_hint}」相关的 {topic} 任务，步骤尽量一致。",
                    priority=0.9 - 0.05 * success,
                )
            )
            continue

        for skill in topic_skills:
            if skill.status == SkillStatus.unverified and skill.usage_count == 0:
                items.append(
                    CurriculumItem(
                        kind=CurriculumKind.verify,
                        topic=topic,
                        title=f"验证 skill：{skill.name}",
                        rationale="技能已合成但尚未在对话中召回使用。",
                        suggested_prompt=f"请按已学的 {skill.name} 流程处理：{skill.triggers[:2]}",
                        priority=0.75,
                        related_skill=skill.name,
                    )
                )
            elif skill.status == SkillStatus.active and skill.confidence < 0.7:
                items.append(
                    CurriculumItem(
                        kind=CurriculumKind.reinforce,
                        topic=topic,
                        title=f"巩固 skill：{skill.name}",
                        rationale=f"active 但置信度仅 {skill.confidence:.2f}。",
                        suggested_prompt=f"再练一次 {skill.name} 相关任务（{kw_hint}）。",
                        priority=0.6,
                        related_skill=skill.name,
                    )
                )

    correction_n = stats.get("correction", {}).get("corrections", 0)
    if correction_n > 0:
        items.append(
            CurriculumItem(
                kind=CurriculumKind.recover,
                topic="correction",
                title="复习近期纠正过的做法",
                rationale=f"累计 {correction_n} 条用户纠正，建议用正确流程再走一遍。",
                suggested_prompt="请根据我之前的纠正，用更新后的正确步骤完成同类任务。",
                priority=0.85,
            )
        )

    items.sort(key=lambda x: -x.priority)
    return CurriculumPlan(items=items[:max_items], generated_by="rules")


_CURRICULUM_LLM_SYSTEM = """You refine practice suggestions for a personal AI agent.
Given gap/verify items as JSON, return ONLY JSON:
{"items":[{"title":"","suggested_prompt":"","rationale":""}]}
Keep the same number of items; use concise Chinese."""


def propose_curriculum_llm(plan: CurriculumPlan, cfg: dict | None = None) -> CurriculumPlan:
    from agent_platform.evolution.llm_client import chat_json, llm_available

    if not plan.items or not llm_available(cfg):
        return plan
    blob = [
        {
            "kind": i.kind.value,
            "topic": i.topic,
            "title": i.title,
            "suggested_prompt": i.suggested_prompt,
            "rationale": i.rationale,
        }
        for i in plan.items
    ]
    data = chat_json(_CURRICULUM_LLM_SYSTEM, str(blob), cfg)
    if not data or not data.get("items"):
        return plan
    refined = []
    for orig, patch in zip(plan.items, data["items"]):
        refined.append(
            orig.model_copy(
                update={
                    "title": str(patch.get("title") or orig.title)[:120],
                    "suggested_prompt": str(patch.get("suggested_prompt") or orig.suggested_prompt)[:300],
                    "rationale": str(patch.get("rationale") or orig.rationale)[:300],
                    "metadata": {**orig.metadata, "curriculum_refiner": "llm"},
                }
            )
        )
    return CurriculumPlan(items=refined, generated_by="llm")


def propose_curriculum(
    experiences: list[ExperienceRecord],
    skills: list[SkillRecord],
    cfg: dict | None = None,
) -> CurriculumPlan:
    cfg = cfg or {}
    mode = str((cfg.get("phase4") or {}).get("curriculum_mode", "rules")).lower()
    plan = propose_curriculum_rules(experiences, skills, cfg)
    if mode == "llm":
        return propose_curriculum_llm(plan, cfg) if plan.items else plan
    if mode == "auto" and plan.items:
        llm_plan = propose_curriculum_llm(plan, cfg)
        if llm_plan.items:
            return llm_plan
    return plan


def format_curriculum_plan(plan: CurriculumPlan) -> str:
    if not plan.items:
        return ""
    lines = ["[Evolution — Suggested Practice]"]
    for i, item in enumerate(plan.items, 1):
        lines.append(f"{i}. ({item.kind.value}) {item.title}")
        lines.append(f"   why: {item.rationale[:160]}")
        lines.append(f"   try: {item.suggested_prompt[:160]}")
    return "\n".join(lines)
