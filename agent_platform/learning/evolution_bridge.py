"""Learning → C7 evolution bridge (Phase 7)."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from agent_platform.evolution.contracts import SkillRecord, SkillStatus
from agent_platform.evolution.store import EvolutionStore
from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import (
    GapMap,
    GapSnapshot,
    GapStatus,
    SkillPromotionResult,
    utc_now,
)
from agent_platform.learning.gap_map import GapMapService
from agent_platform.learning.remediation_skills import skill_for_error_code
from agent_platform.learning.store import (
    append_gap_snapshot,
    layout_for,
    latest_gap_snapshots,
)


def _skill_name(student_id: str, error_code: str) -> str:
    return f"student/{student_id}/remediation-{error_code.lower()}"


class LearningEvolutionBridge:
    def __init__(
        self,
        data_root: Optional[Path] = None,
        gap_svc: Optional[GapMapService] = None,
    ) -> None:
        self._cfg = load_student_learning_config()
        self._data_root = data_root
        self._gaps = gap_svc or GapMapService(data_root=data_root)

    def _store(self, student_id: str) -> EvolutionStore:
        lay = layout_for(student_id, self._data_root)
        lay.evolution_dir.mkdir(parents=True, exist_ok=True)
        return EvolutionStore(root=lay.evolution_dir)

    def _record_snapshots(self, student_id: str, gap_map: GapMap) -> None:
        lay = layout_for(student_id, self._data_root)
        now = utc_now()
        for gap in gap_map.gaps:
            append_gap_snapshot(
                lay.gap_snapshots_path,
                GapSnapshot(
                    gap_id=gap.gap_id,
                    wrong_7d=gap.stats.wrong_7d,
                    status=gap.status,
                    recorded_at=now,
                ),
            )

    def evaluate_after_attempt(self, student_id: str, gap_map: GapMap) -> list[SkillPromotionResult]:
        evo_cfg = self._cfg.get("evolution") or {}
        if not evo_cfg.get("enabled", True):
            return []

        lay = layout_for(student_id, self._data_root)
        previous = latest_gap_snapshots(lay.gap_snapshots_path)
        store = self._store(student_id)
        existing = {s.name: s for s in store.list_skills()}
        results: list[SkillPromotionResult] = []

        for gap in gap_map.gaps:
            prev = previous.get(gap.gap_id)
            should_promote = False
            reason = ""

            if evo_cfg.get("promote_on_mastered", True) and gap.status == GapStatus.mastered:
                should_promote = True
                reason = "gap_mastered"
            elif (
                evo_cfg.get("promote_on_wrong_7d_drop", True)
                and prev
                and prev.wrong_7d >= int((self._cfg.get("proactive") or {}).get("gap_recurrence_threshold", 3))
                and gap.stats.wrong_7d < prev.wrong_7d
            ):
                should_promote = True
                reason = "wrong_7d_drop"

            if not should_promote:
                continue

            remediation = skill_for_error_code(gap.error_code)
            name = _skill_name(student_id, gap.error_code)
            confidence = 0.85 if gap.status == GapStatus.mastered else 0.65
            status = SkillStatus.active if gap.status == GapStatus.mastered else SkillStatus.unverified

            if name in existing:
                skill = existing[name]
                skill.confidence = max(skill.confidence, confidence)
                if gap.status == GapStatus.mastered:
                    skill.status = SkillStatus.active
                store.save_skill(skill)
                results.append(
                    SkillPromotionResult(
                        gap_id=gap.gap_id,
                        error_code=gap.error_code,
                        skill_name=name,
                        promoted=True,
                        reason=f"{reason}_updated",
                        confidence=skill.confidence,
                    )
                )
                continue

            skill = SkillRecord(
                name=name,
                description=f"个人补救策略：{gap.title}",
                topic=f"learning/{gap.knowledge_point_id}",
                triggers=[gap.title, gap.error_code, gap.gap_id],
                procedure=remediation.procedure.strip(),
                guardrails="需结合 gap_map 证据；无 attempt 不得声称掌握。",
                success_criteria=f"gap {gap.gap_id} wrong_7d 下降或 mastered",
                confidence=confidence,
                status=status,
                metadata={
                    "student_id": student_id,
                    "gap_id": gap.gap_id,
                    "error_code": gap.error_code,
                    "source": "learning_evolution_bridge",
                },
            )
            store.save_skill(skill)
            results.append(
                SkillPromotionResult(
                    gap_id=gap.gap_id,
                    error_code=gap.error_code,
                    skill_name=name,
                    promoted=True,
                    reason=reason,
                    confidence=confidence,
                )
            )

        self._record_snapshots(student_id, gap_map)
        return results

    def list_personal_skills(self, student_id: str) -> list[SkillRecord]:
        return self._store(student_id).list_skills()
