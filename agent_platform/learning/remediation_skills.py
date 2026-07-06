"""Static remediation skills loader (Phase 6)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import yaml

from agent_platform.learning.contracts import RemediationSkill

_SKILLS_DIR = Path(__file__).resolve().parent / "skills" / "remediation"

_DEFAULT_BY_ERROR = {
    "CONCEPT_DOMAIN": "remediation/concept_v1",
    "READING_ERROR": "remediation/concept_v1",
    "EN_READING_ERROR": "remediation/concept_v1",
    "MISS_MULTIPLY_AFTER_DENOM": "remediation/procedure_checklist",
    "PROCEDURE_ERROR": "remediation/procedure_checklist",
    "CALCULATION_ERROR": "remediation/procedure_checklist",
    "SPELLING_ERROR": "remediation/english_vocab_drill",
    "VOCAB_GAP": "remediation/english_vocab_drill",
    "GRAMMAR_ERROR": "remediation/concept_v1",
}


@lru_cache(maxsize=1)
def load_remediation_skills() -> dict[str, RemediationSkill]:
    skills: dict[str, RemediationSkill] = {}
    for path in sorted(_SKILLS_DIR.glob("*.yaml")):
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        skill = RemediationSkill.model_validate(data)
        skills[skill.skill_id] = skill
    return skills


def skill_for_error_code(error_code: str) -> RemediationSkill:
    skills = load_remediation_skills()
    sid = _DEFAULT_BY_ERROR.get(error_code, "remediation/socratic_hint_flow")
    return skills[sid]


def list_skill_ids() -> list[str]:
    return sorted(load_remediation_skills().keys())
