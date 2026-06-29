"""C7 Phase 1 tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.evolution.extract import extract_experience
from agent_platform.evolution.service import EvolutionService
from agent_platform.evolution.store import EvolutionStore


def test_extract_skips_trivial():
    assert extract_experience("hi", "hello") is None


def test_l1_l2_recall_flow():
    td = Path(tempfile.mkdtemp())
    svc = EvolutionService(store=EvolutionStore(root=td))
    for i in range(3):
        svc.on_turn_complete(
            f"导出周报 fetch markdown 第{i+1}次",
            "使用 fetch 拉取并写 markdown 周报。",
        )
    skills = svc.synthesize_skills()
    assert skills
    hits = svc.recall_skills("周报 fetch")
    assert hits
