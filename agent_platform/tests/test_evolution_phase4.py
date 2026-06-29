"""C7 Phase 4 tests — curriculum."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.evolution.contracts import CurriculumKind, CurriculumLogSource
from agent_platform.evolution.curriculum import propose_curriculum_rules
from agent_platform.evolution.service import EvolutionService
from agent_platform.evolution.store import EvolutionStore


def _phase4_cfg(**overrides) -> dict:
    base = {
        "phase3": {"extract_mode": "rules", "synthesize_mode": "rules"},
        "phase4": {
            "curriculum_enabled": True,
            "curriculum_mode": "rules",
            "inject_in_pre_llm": True,
            "inject_when_no_recall": True,
            "inject_always": False,
            "max_suggestions": 3,
            "min_experiences_for_gap": 2,
            "log_curriculum": True,
        },
        "bridge": {"post_llm_detect_correction": False},
        "orchestrator": {"l2_every_n_experiences": 99},
        "synthesize": {"min_experiences_per_skill": 3, "min_shared_keywords": 2},
    }
    if overrides:
        base.update(overrides)
    return base


def test_gap_curriculum():
    td = Path(tempfile.mkdtemp())
    cfg = _phase4_cfg()
    svc = EvolutionService(store=EvolutionStore(root=td), config=cfg)
    svc.on_turn_complete("导出周报 fetch markdown A", "使用 fetch 写 markdown。")
    svc.on_turn_complete("导出周报 fetch markdown B", "再次 fetch 并 markdown。")
    plan = propose_curriculum_rules(svc.store.list_experiences(), svc.store.list_skills(), cfg)
    assert any(i.kind == CurriculumKind.gap for i in plan.items)


def test_curriculum_log_on_inject_and_tool():
    td = Path(tempfile.mkdtemp())
    cfg = _phase4_cfg()
    store = EvolutionStore(root=td)
    svc = EvolutionService(store=store, config=cfg)
    svc.on_turn_complete("导出周报 fetch markdown A", "使用 fetch 写 markdown。")
    svc.on_turn_complete("导出周报 fetch markdown B", "再次 fetch 并 markdown。")

    ctx = svc.format_evolution_context_for_prompt("unrelated weather question xyz")
    assert "Suggested Practice" in ctx
    plan, _ = svc.curriculum_for_tool()
    assert plan.items

    logs = store.list_curriculum_log()
    assert len(logs) == 2
    assert logs[0].source == CurriculumLogSource.pre_llm
    assert logs[0].injected is True
    assert logs[1].source == CurriculumLogSource.tool
    assert store.curriculum_log_path.is_file()
