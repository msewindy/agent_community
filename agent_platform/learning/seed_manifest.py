"""Seed data package verification (Phase 7 / P0 pivot)."""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_platform.learning._config import load_student_learning_config, repo_root
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.remediation_skills import list_skill_ids
from agent_platform.learning.taxonomy import TaxonomyService


@dataclass
class SeedVerifyResult:
    ok: bool
    question_count: int
    taxonomy_count: int
    remediation_skill_count: int
    unit_counts: dict[str, int] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)


def verify_seed_package() -> SeedVerifyResult:
    cfg = load_student_learning_config()
    seed_cfg = cfg.get("seed") or {}
    min_q = int(seed_cfg.get("min_questions", 10))
    target_q = int(seed_cfg.get("target_questions", 30))
    min_tax = int(seed_cfg.get("min_taxonomy_codes", 5))
    min_skills = int(seed_cfg.get("min_remediation_skills", 4))
    pilot_units = list(seed_cfg.get("pilot_units") or [])

    warnings: list[str] = []
    errors: list[str] = []

    bank = QuestionBankService()
    all_questions = bank.list_questions()
    q_count = len(all_questions)

    unit_counts: dict[str, int] = {}
    for u in pilot_units:
        unit_counts[u] = len(bank.list_questions(unit_id=u))

    tax = TaxonomyService(cfg)
    tax_count = len(tax.list_codes())

    skill_count = len(list_skill_ids())

    if q_count < min_q:
        errors.append(f"questions {q_count} < min {min_q}")
    elif q_count < target_q:
        warnings.append(f"questions {q_count} below pilot target {target_q}")

    for u in pilot_units:
        if unit_counts.get(u, 0) < min_q:
            warnings.append(f"unit {u} has {unit_counts.get(u, 0)} questions (< {min_q})")

    if tax_count < min_tax:
        errors.append(f"taxonomy codes {tax_count} < min {min_tax}")

    if skill_count < min_skills:
        errors.append(f"remediation skills {skill_count} < min {min_skills}")

    catalog_path = repo_root() / (cfg.get("kp_catalog") or {}).get(
        "path",
        "agent_platform/learning/catalog/kp_catalog.json",
    )
    if not catalog_path.is_file():
        errors.append("kp_catalog.json missing")
    else:
        KpCatalogService(catalog_path=catalog_path)

    wiki_path = repo_root() / "agent_platform" / "wiki" / "data"
    if not wiki_path.is_dir():
        warnings.append("wiki data dir not found (P0 target: required for pilot units)")

    return SeedVerifyResult(
        ok=not errors,
        question_count=q_count,
        taxonomy_count=tax_count,
        remediation_skill_count=skill_count,
        unit_counts=unit_counts,
        warnings=warnings,
        errors=errors,
    )
