"""家庭 Alpha 启动自检：题库导入 + 种子包校验 + 知识点库概览。"""

from __future__ import annotations

from dataclasses import dataclass, field

from agent_platform.learning import sqlite_store
from agent_platform.learning.kp_catalog import get_kp_catalog_service
from agent_platform.learning.question_bank import QuestionBankService
from agent_platform.learning.seed_manifest import verify_seed_package


@dataclass
class BootstrapReport:
    ok: bool
    questions_imported: int = 0
    question_count: int = 0
    catalog_units: int = 0
    catalog_kp_count: int = 0
    wiki_pages_bootstrapped: int = 0
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "ok": self.ok,
            "questions_imported": self.questions_imported,
            "question_count": self.question_count,
            "catalog_units": self.catalog_units,
            "catalog_kp_count": self.catalog_kp_count,
            "wiki_pages_bootstrapped": self.wiki_pages_bootstrapped,
            "warnings": self.warnings,
            "errors": self.errors,
        }


def ensure_family_alpha_content(*, import_bank: bool = True) -> BootstrapReport:
    """确保试用所需题库与 catalog 就绪；服务启动时调用一次即可。"""
    warnings: list[str] = []
    errors: list[str] = []
    imported = 0

    bank = QuestionBankService()
    need_import = import_bank and (
        not bank.uses_sqlite
        or sqlite_store.count_questions(bank.sqlite_path) == 0
    )
    if need_import:
        try:
            imported = bank.import_seed_to_sqlite()
        except Exception as exc:  # noqa: BLE001
            errors.append(f"question bank import failed: {exc}")
        bank = QuestionBankService()

    verify = verify_seed_package()
    warnings.extend(verify.warnings)
    errors.extend(verify.errors)

    catalog = get_kp_catalog_service()
    kp_count = sum(len(u.knowledge_points) for u in catalog.catalog.units)
    if catalog.catalog.units == 0:
        errors.append("kp catalog has no units")

    wiki_bootstrapped = 0
    try:
        from agent_platform.learning.kp_wiki_sync import bootstrap_pilot_kp_wiki

        wiki_report = bootstrap_pilot_kp_wiki(catalog=catalog)
        wiki_bootstrapped = wiki_report.pages_synced
        warnings.extend(wiki_report.warnings)
    except Exception as exc:  # noqa: BLE001
        warnings.append(f"kp wiki bootstrap skipped: {exc}")

    return BootstrapReport(
        ok=not errors,
        questions_imported=imported,
        question_count=verify.question_count,
        catalog_units=len(catalog.catalog.units),
        catalog_kp_count=kp_count,
        wiki_pages_bootstrapped=wiki_bootstrapped,
        warnings=warnings,
        errors=errors,
    )
