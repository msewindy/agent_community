"""C7 Phase 3 tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.evolution.contracts import SkillRecord, SkillStatus
from agent_platform.evolution.service import EvolutionService
from agent_platform.evolution.store import EvolutionStore
from agent_platform.evolution.validate import looks_like_user_correction


def test_correction_detection():
    cfg = {"l5": {"correction_keywords": ["不对"]}}
    assert looks_like_user_correction("不对，应该用别的", cfg)


def test_lifecycle_promote_and_correct():
    td = Path(tempfile.mkdtemp())
    cfg = {
        "phase3": {"extract_mode": "rules", "synthesize_mode": "rules"},
        "lifecycle": {"promote_after_uses": 2, "demote_on_correction": 0.2},
        "bridge": {"post_llm_detect_correction": False},
    }
    store = EvolutionStore(root=td)
    svc = EvolutionService(store=store, config=cfg)
    skill = SkillRecord(
        name="workflow_fetch_md",
        topic="workflow",
        triggers=["fetch", "markdown"],
        procedure="fetch then markdown",
        confidence=0.6,
    )
    store.save_skill(skill)
    svc.record_skill_recall("fetch markdown")
    svc.record_skill_recall("fetch markdown")
    updated = store.list_skills()[0]
    assert updated.status == SkillStatus.active
    svc.on_user_correction("不对，别用 markdown", "use obsidian")
    demoted = store.list_skills()[0]
    assert demoted.confidence < 0.6
