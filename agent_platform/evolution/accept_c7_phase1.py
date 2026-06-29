#!/usr/bin/env python3
"""C7 Phase 1 acceptance — L1 experience + L2 skill + recall."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.evolution.service import EvolutionService
from agent_platform.evolution.store import EvolutionStore


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def main() -> int:
    td = Path(tempfile.mkdtemp(prefix="c7_phase1_"))
    store = EvolutionStore(root=td)
    cfg = {
        "phase3": {"extract_mode": "rules", "synthesize_mode": "rules"},
        "bridge": {"post_llm_detect_correction": False},
        "orchestrator": {"l2_every_n_experiences": 3},
    }
    svc = EvolutionService(store=store, config=cfg)

    # A1: trivial turn skipped
    r0 = svc.on_turn_complete("hi", "hello")
    if r0["stored"]:
        _fail("A1 trivial turn should not store")
        return 1
    _ok("A1 trivial turn filtered")

    # A2: accumulate workflow experiences
    turns = [
        ("请帮我导出周报，包含 fetch 和 markdown 步骤", "先 fetch URL，再整理为 markdown 周报结构。"),
        ("再次导出周报，和上次一样用 fetch 整理 markdown", "沿用 fetch → markdown 流程生成周报。"),
        ("导出周报流程：fetch 后写 markdown 摘要", "使用 fetch 拉取内容并写入 markdown 摘要。"),
    ]
    for u, a in turns:
        svc.on_turn_complete(u, a)

    exps = store.list_experiences()
    if len(exps) < 3:
        _fail(f"A2 expected >=3 experiences, got {len(exps)}")
        return 1
    _ok(f"A2 stored {len(exps)} experiences")

    skills = svc.synthesize_skills()
    if not skills:
        _fail("A3 expected at least one synthesized skill")
        return 1
    _ok(f"A3 synthesized {len(skills)} skill(s): {skills[0].name}")

    recalled = svc.recall_skills("导出周报 fetch markdown")
    if not recalled:
        _fail("A4 recall should hit workflow skill")
        return 1
    _ok(f"A4 recall hits skill {recalled[0].name}")

    ctx = svc.format_recall_for_prompt("导出周报 fetch markdown")
    if "procedure" not in ctx.lower() and "fetch" not in ctx.lower():
        _fail("A5 prompt context missing procedure")
        return 1
    _ok("A5 prompt context formatted")

    svc.record_correction("不对，应该用 obsidian 而不是 markdown", "改用 obsidian 路径")
    if not any(e.task_success is False for e in store.list_experiences()):
        _fail("A6 correction experience not stored")
        return 1
    _ok("A6 user correction stored as negative experience")

    print()
    print("accept_c7_phase1: PASS — L1 + L2 + recall OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
