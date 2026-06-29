#!/usr/bin/env python3
"""C7 Phase 4 acceptance — Curriculum + Hermes tool integration."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

from agent_platform.evolution.contracts import CurriculumKind, CurriculumLogSource, SkillRecord, SkillStatus
from agent_platform.evolution.service import EvolutionService
from agent_platform.evolution.store import EvolutionStore
import agent_platform.integrations.hermes.evolution_tools as et


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def _base_cfg() -> dict:
    return {
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


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="c7_phase4_"))
    store = EvolutionStore(root=td)
    svc = EvolutionService(store=store, config=_base_cfg())
    et._svc = svc  # type: ignore[attr-defined]

    # D1: gap suggestion when 2 successes but no skill
    svc.on_turn_complete("导出周报 fetch markdown A", "使用 fetch 写 markdown。")
    svc.on_turn_complete("导出周报 fetch markdown B", "再次 fetch 并 markdown。")
    plan = svc.propose_curriculum_plan()
    gaps = [i for i in plan.items if i.kind == CurriculumKind.gap]
    if not gaps or gaps[0].topic not in ("workflow", "tools"):
        _fail(f"D1 expected workflow/tools gap curriculum, got {[ (i.kind, i.topic) for i in plan.items ]}")
        return 1
    _ok(f"D1 gap curriculum for topic={gaps[0].topic}")

    # D2: verify suggestion for unverified unused skill
    skill = SkillRecord(
        name="tools_fetch_markdown",
        topic="workflow",
        triggers=["fetch", "markdown"],
        procedure="fetch then markdown",
        confidence=0.6,
        status=SkillStatus.unverified,
    )
    store.save_skill(skill)
    plan2 = svc.propose_curriculum_plan()
    verifies = [i for i in plan2.items if i.kind == CurriculumKind.verify]
    if not verifies:
        _fail("D2 expected verify curriculum for unused skill")
        return 1
    _ok("D2 verify curriculum for unverified skill")

    # D3: recover after correction
    svc.on_user_correction("不对，应该用 obsidian", "改用 obsidian")
    plan3 = svc.propose_curriculum_plan()
    if not any(i.kind == CurriculumKind.recover for i in plan3.items):
        _fail("D3 expected recover curriculum after correction")
        return 1
    _ok("D3 recover curriculum after user correction")

    # D4: pre_llm injects curriculum when no skill recall
    inj = et.pre_llm_recall_hook(user_message="今天天气怎么样")
    if not inj or "Suggested Practice" not in inj.get("context", ""):
        _fail("D4 expected curriculum in pre_llm when no recall")
        return 1
    _ok("D4 pre_llm injects curriculum when recall empty")

    # D5: curriculum tool
    payload = json.loads(et.agent_evolution_curriculum({}))
    if not payload.get("success") or payload.get("count", 0) < 1:
        _fail(f"D5 curriculum tool failed: {payload}")
        return 1
    _ok(f"D5 agent_evolution_curriculum tool ({payload.get('count')} items)")

    # D6: hooks register curriculum tool
    ctx = SimpleNamespace(_hooks={}, _tools=[], register_hook=lambda n, fn: ctx._hooks.setdefault(n, []).append(fn), register_tool=lambda **kw: ctx._tools.append(kw))
    et.register_evolution_hermes_tools(ctx)
    names = {t.get("name") for t in ctx._tools}
    if "agent_evolution_curriculum" not in names:
        _fail(f"D6 missing curriculum tool registration: {names}")
        return 1
    _ok("D6 Hermes tools include agent_evolution_curriculum")

    # D7: curriculum suggestions persisted to curriculum_log.jsonl
    et.pre_llm_recall_hook(user_message="随便聊聊 unrelated topic xyz")
    json.loads(et.agent_evolution_curriculum({}))
    logs = store.list_curriculum_log()
    if len(logs) < 2:
        _fail(f"D7 expected >=2 curriculum log entries, got {len(logs)}")
        return 1
    sources = {row.source for row in logs}
    if CurriculumLogSource.pre_llm not in sources or CurriculumLogSource.tool not in sources:
        _fail(f"D7 expected pre_llm + tool sources, got {sources}")
        return 1
    if not store.curriculum_log_path.is_file():
        _fail("D7 curriculum_log.jsonl missing on disk")
        return 1
    _ok(f"D7 curriculum_log.jsonl ({len(logs)} entries, sources={sorted(s.value for s in sources)})")

    print()
    print("accept_c7_phase4: PASS — Curriculum + hooks OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
