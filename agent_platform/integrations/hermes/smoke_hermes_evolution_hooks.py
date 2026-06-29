#!/usr/bin/env python3
"""C7 Phase 2 — smoke Hermes evolution hooks without full Hermes CLI."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="evo_hook_smoke_"))
    import os

    os.environ["AGENT_COMMUNITY_ROOT"] = str(
        Path(__file__).resolve().parents[3]
    )

    from agent_platform.evolution.store import EvolutionStore
    from agent_platform.evolution.service import EvolutionService
    import agent_platform.integrations.hermes.evolution_tools as et

    store = EvolutionStore(root=td)
    cfg = {
        "phase3": {"extract_mode": "rules", "synthesize_mode": "rules"},
        "bridge": {"post_llm_detect_correction": False},
        "orchestrator": {"l2_every_n_experiences": 3},
    }
    svc = EvolutionService(store=store, config=cfg)
    et._svc = svc  # type: ignore[attr-defined]

    # Seed experiences + skill
    for i in range(3):
        svc.on_turn_complete(
            f"导出周报 fetch markdown 轮次{i+1}",
            "使用 fetch 拉取并写 markdown 周报。",
        )
    svc.synthesize_skills()

    inj = et.pre_llm_recall_hook(user_message="请再导出一次周报 fetch")
    if not inj or "context" not in inj or "fetch" not in inj["context"].lower():
        print("smoke_hermes_evolution_hooks: FAIL pre_llm inject", file=sys.stderr)
        return 1

    et.post_llm_evolve_hook(
        user_message="请再导出一次周报",
        assistant_response="好的，按 fetch → markdown 流程生成。",
    )

    ctx = SimpleNamespace(
        _hooks={},
        _tools=[],
        register_hook=lambda name, fn: ctx._hooks.setdefault(name, []).append(fn),
        register_tool=lambda **kw: ctx._tools.append(kw),
    )
    et.register_evolution_hermes_tools(ctx)
    if "pre_llm_call" not in ctx._hooks or "post_llm_call" not in ctx._hooks:
        print("smoke_hermes_evolution_hooks: FAIL hooks not registered", file=sys.stderr)
        return 1
    tool_names = {t.get("name") for t in ctx._tools}
    if "agent_evolution_curriculum" not in tool_names:
        print("smoke_hermes_evolution_hooks: FAIL curriculum tool missing", file=sys.stderr)
        return 1

    status = json.loads(et.agent_evolution_status({}))
    if not status.get("success") or status.get("skill_count", 0) < 1:
        print("smoke_hermes_evolution_hooks: FAIL status", status, file=sys.stderr)
        return 1

    print("smoke_hermes_evolution_hooks: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
