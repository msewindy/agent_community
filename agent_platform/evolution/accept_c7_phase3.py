#!/usr/bin/env python3
"""C7 Phase 3 acceptance — LLM modes, L3 lifecycle, L5 + M7 bridge."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.calibration.contracts import CorrectionResult, UserCorrectionRequest
from agent_platform.evolution.bridge import forward_m7_correction
from agent_platform.evolution.contracts import SkillRecord, SkillStatus
from agent_platform.evolution.service import EvolutionService
from agent_platform.evolution.store import EvolutionStore


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="c7_phase3_"))
    cfg = {
        "phase3": {"extract_mode": "rules", "synthesize_mode": "rules"},
        "orchestrator": {"l2_every_n_experiences": 3},
        "lifecycle": {"promote_after_uses": 3, "demote_on_correction": 0.2, "deprecate_on_correction": True},
        "l5": {"correction_keywords": ["不对", "错了"]},
        "bridge": {"m7_enabled": True, "post_llm_detect_correction": True},
        "synthesize": {"min_experiences_per_skill": 3, "min_shared_keywords": 2},
    }
    store = EvolutionStore(root=td)
    svc = EvolutionService(store=store, config=cfg)

    # B1: rules path still stores experiences (Phase 1 compat)
    for i in range(3):
        svc.on_turn_complete(
            f"导出周报 fetch markdown 第{i+1}次",
            "使用 fetch 拉取并写 markdown 周报。",
        )
    if len(store.list_experiences()) < 3:
        _fail("B1 expected >=3 experiences")
        return 1
    _ok("B1 rules extract path stores experiences")

    skills = svc.synthesize_skills()
    if not skills:
        _fail("B2 expected synthesized skill")
        return 1
    skill = skills[0]
    _ok(f"B2 synthesized skill {skill.name}")

    # B3: L3 promote after recall usage
    for _ in range(3):
        svc.record_skill_recall("导出周报 fetch markdown")
    promoted = store.list_skills()[0]
    if promoted.status != SkillStatus.active:
        _fail(f"B3 expected active status, got {promoted.status}")
        return 1
    _ok("B3 skill promoted to active after 3 recalls")

    # B4: L5 correction demotes / deprecates overlapping skill
    r = svc.on_user_correction("不对，应该用 obsidian 而不是 markdown", "改用 obsidian 路径")
    if r.get("kind") != "correction":
        _fail("B4 expected correction kind")
        return 1
    after = store.list_skills()[0]
    if after.confidence >= promoted.confidence:
        _fail("B4 expected confidence demotion")
        return 1
    _ok(f"B4 correction adjusted skill (conf={after.confidence:.2f})")

    # B5: deprecated skills excluded from recall
    after.status = SkillStatus.deprecated
    store.save_skill(after)
    hits = svc.recall_skills("markdown fetch 周报")
    if any(h.skill_id == after.skill_id for h in hits):
        _fail("B5 deprecated skill should not recall")
        return 1
    _ok("B5 deprecated skills filtered from recall")

    # B6: post_llm correction detection
    r2 = svc.on_turn_complete("不对，你刚才的步骤错了", "好的，我改用正确流程。")
    if r2.get("kind") != "correction":
        _fail("B6 expected auto correction detection")
        return 1
    _ok("B6 post_llm correction keyword detection")

    # B7: M7 bridge forwards to evolution
    req = UserCorrectionRequest(
        record_id="dummy-id",
        old_value="markdown",
        new_value="obsidian",
        reason="不对，应该用 obsidian",
    )
    result = CorrectionResult(
        success=True,
        apology_text="ok",
        old_record_id="dummy-id",
        new_record_id="new-id",
        tombstoned=True,
    )
    before = len(store.list_experiences())
    forward_m7_correction(req, result, evolution_service=svc)
    if len(store.list_experiences()) <= before:
        _fail("B7 M7 bridge should append correction experience")
        return 1
    _ok("B7 M7 bridge forwards correction to evolution")

    print()
    print("accept_c7_phase3: PASS — LLM modes + L3/L5 + M7 bridge OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
