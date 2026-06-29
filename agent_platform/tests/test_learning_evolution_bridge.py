"""Phase 7 — evolution bridge tests."""

from __future__ import annotations

from pathlib import Path

from agent_platform.learning.attempt import AttemptService
from agent_platform.learning.evolution_bridge import LearningEvolutionBridge
from agent_platform.learning.student_context import StudentContextService
from agent_platform.evolution.contracts import SkillStatus


def test_mastered_gap_promotes_personal_skill(tmp_path: Path) -> None:
    root = tmp_path / "student_data"
    ctx_svc = StudentContextService(data_root=root)
    sid = "evo-stu-1"
    ctx_svc.init_from_defaults(sid)
    bridge = LearningEvolutionBridge(data_root=root)
    att = AttemptService(data_root=root, context_svc=ctx_svc, evolution_bridge=bridge)

    for _ in range(3):
        att.submit(sid, "q-g2m-002", "80")
    att.submit(sid, "q-g2m-002", "85")
    att.submit(sid, "q-g2m-003", "83")
    result = att.submit(sid, "q-g2m-009", "75")

    assert any(p.promoted for p in result.skill_promotions)
    skills = bridge.list_personal_skills(sid)
    assert skills
    assert skills[0].status == SkillStatus.active
