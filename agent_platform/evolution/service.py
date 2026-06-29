"""evolution_service facade — L1 ingest, L2 synthesize, recall, Phase 3 lifecycle."""

from __future__ import annotations

from functools import lru_cache
from typing import Optional

from agent_platform.evolution._config import load_evolution_config
from agent_platform.evolution.contracts import (
    CurriculumLogEntry,
    CurriculumLogSource,
    CurriculumPlan,
    ExperienceRecord,
    SkillRecord,
)
from agent_platform.evolution.curriculum import format_curriculum_plan, propose_curriculum
from agent_platform.evolution.extract import extract_experience_from_turn
from agent_platform.evolution.lifecycle import (
    apply_correction_to_skills,
    filter_recallable_skills,
    record_skill_usage,
)
from agent_platform.evolution.store import EvolutionStore
from agent_platform.evolution.synthesize import synthesize_skills_from_experiences
from agent_platform.evolution.validate import (
    build_correction_experience,
    filter_validated_skills,
    looks_like_user_correction,
)


class EvolutionService:
    def __init__(self, store: Optional[EvolutionStore] = None, config: Optional[dict] = None) -> None:
        self._cfg = config or load_evolution_config()
        self._store = store or EvolutionStore()
        self._l1_count = 0

    @property
    def store(self) -> EvolutionStore:
        return self._store

    def on_turn_complete(self, user_message: str, assistant_message: str) -> dict:
        """L1 extract + store; trigger L2 every N experiences."""
        bridge = self._cfg.get("bridge") or {}
        if bridge.get("post_llm_detect_correction", True) and looks_like_user_correction(
            user_message, self._cfg
        ):
            return self.on_user_correction(user_message, assistant_message)

        exp = extract_experience_from_turn(user_message, assistant_message, self._cfg)
        result = {"stored": False, "experience_id": None, "skills_generated": 0, "kind": "turn"}
        if exp is None:
            return result

        self._store.append_experience(exp)
        self._l1_count += 1
        result["stored"] = True
        result["experience_id"] = exp.experience_id

        every = int((self._cfg.get("orchestrator") or {}).get("l2_every_n_experiences", 3))
        if self._l1_count % every == 0:
            skills = self.synthesize_skills()
            result["skills_generated"] = len(skills)
        return result

    def on_user_correction(
        self,
        user_message: str,
        correction_note: str,
        *,
        old_value: str | None = None,
        new_value: str | None = None,
        trace_id: str | None = None,
    ) -> dict:
        """L5 + M7 bridge: store negative experience and adjust skills."""
        skills = self._store.list_skills()
        updated = apply_correction_to_skills(skills, user_message, correction_note, self._cfg)
        for skill in updated:
            self._store.save_skill(skill)

        note = correction_note
        if old_value and new_value:
            note = f"{old_value} → {new_value}"
        exp = build_correction_experience(
            user_message,
            note,
            linked_skill_ids=[s.skill_id for s in updated],
        )
        if trace_id:
            exp.metadata["trace_id"] = trace_id
        self._store.append_experience(exp)
        return {
            "stored": True,
            "kind": "correction",
            "experience_id": exp.experience_id,
            "skills_adjusted": len(updated),
            "skills_generated": 0,
        }

    def synthesize_skills(self) -> list[SkillRecord]:
        exps = self._store.list_experiences()
        skills = synthesize_skills_from_experiences(exps, self._cfg)
        for s in skills:
            self._store.save_skill(s)
        return skills

    def recall_skills(self, query: str, top_k: int | None = None) -> list[SkillRecord]:
        top_k = top_k or int((self._cfg.get("recall") or {}).get("top_k", 5))
        q = query.lower()
        q_tokens = set(q.split())
        scored: list[tuple[float, SkillRecord]] = []
        for skill in filter_recallable_skills(self._store.list_skills()):
            match_score = 0.0
            for t in skill.triggers:
                tl = t.lower()
                if tl in q or tl in q_tokens:
                    match_score += 2.0
                if any(tok in tl for tok in q_tokens if len(tok) >= 2):
                    match_score += 0.5
            if skill.topic.lower() in q:
                match_score += 1.0
            if match_score <= 0:
                continue
            score = match_score + skill.confidence * 0.5
            scored.append((score, skill))
        scored.sort(key=lambda x: -x[0])
        hits = [s for _, s in scored[:top_k]]
        return filter_validated_skills(hits, query)

    def record_skill_recall(self, query: str) -> None:
        """L3: bump usage for skills injected into a turn."""
        for skill in self.recall_skills(query):
            updated = record_skill_usage(skill, self._cfg)
            self._store.save_skill(updated)

    def format_curriculum_for_prompt(self) -> str:
        p4 = self._cfg.get("phase4") or {}
        if not p4.get("curriculum_enabled", True):
            return ""
        plan = propose_curriculum(
            self._store.list_experiences(),
            self._store.list_skills(),
            self._cfg,
        )
        return format_curriculum_plan(plan)

    def _log_curriculum(
        self,
        plan: CurriculumPlan,
        source: CurriculumLogSource,
        *,
        user_query: str = "",
        injected: bool = False,
    ) -> None:
        p4 = self._cfg.get("phase4") or {}
        if not p4.get("log_curriculum", True) or not plan.items:
            return
        entry = CurriculumLogEntry(
            source=source,
            user_query=user_query[:500],
            injected=injected,
            generated_by=plan.generated_by,
            item_count=len(plan.items),
            items=plan.items,
        )
        self._store.append_curriculum_log(entry)

    def propose_curriculum_plan(self) -> CurriculumPlan:
        p4 = self._cfg.get("phase4") or {}
        if not p4.get("curriculum_enabled", True):
            return CurriculumPlan()
        return propose_curriculum(
            self._store.list_experiences(),
            self._store.list_skills(),
            self._cfg,
        )

    def curriculum_for_tool(self) -> tuple[CurriculumPlan, str]:
        """Return plan + prompt block and persist one log entry (tool source)."""
        plan = self.propose_curriculum_plan()
        text = format_curriculum_plan(plan)
        self._log_curriculum(plan, CurriculumLogSource.tool, injected=False)
        return plan, text

    def format_evolution_context_for_prompt(self, query: str) -> str:
        """Combine skill recall + optional curriculum block for pre_llm_call."""
        parts: list[str] = []
        recall = self.format_recall_for_prompt(query)
        if recall:
            parts.append(recall)
        p4 = self._cfg.get("phase4") or {}
        if p4.get("curriculum_enabled", True) and p4.get("inject_in_pre_llm", True):
            inject_always = bool(p4.get("inject_always", False))
            inject_when_no_recall = bool(p4.get("inject_when_no_recall", True))
            if inject_always or (inject_when_no_recall and not recall):
                plan = self.propose_curriculum_plan()
                curriculum = format_curriculum_plan(plan)
                if curriculum:
                    self._log_curriculum(
                        plan,
                        CurriculumLogSource.pre_llm,
                        user_query=query,
                        injected=True,
                    )
                    parts.append(curriculum)
        return "\n\n".join(parts)

    def format_recall_for_prompt(self, query: str) -> str:
        skills = self.recall_skills(query)
        if not skills:
            return ""
        self.record_skill_recall(query)
        lines = ["[Evolution — Recalled Skills]"]
        for i, s in enumerate(skills, 1):
            status = s.status.value if hasattr(s.status, "value") else str(s.status)
            lines.append(f"{i}. {s.name} (topic={s.topic}, conf={s.confidence:.2f}, status={status})")
            lines.append(f"   procedure: {s.procedure[:200]}")
        return "\n".join(lines)

    def record_correction(self, user_message: str, note: str) -> ExperienceRecord:
        """Backward-compatible negative signal API."""
        result = self.on_user_correction(user_message, note)
        exps = self._store.list_experiences()
        return exps[-1] if exps else build_correction_experience(user_message, note)


@lru_cache(maxsize=1)
def get_evolution_service() -> EvolutionService:
    return EvolutionService()
