"""P0 — family alpha bootstrap + catalog hot reload."""

from __future__ import annotations

import json
import time
from pathlib import Path

from agent_platform.learning.bootstrap_family_alpha import ensure_family_alpha_content
from agent_platform.learning.kp_catalog import (
    get_kp_catalog_service,
    invalidate_kp_catalog_cache,
)


def test_ensure_family_alpha_content_imports_bank(tmp_path: Path) -> None:
    db = tmp_path / "questions.db"
    from agent_platform.learning.question_bank import QuestionBankService

    bank = QuestionBankService(
        sqlite_path=db,
        seed_path=Path("agent_platform/learning/question_bank/seed_questions_g3_math_mixed_ops.json"),
    )
    if not bank.uses_sqlite:
        n = bank.import_seed_to_sqlite()
        assert n >= 10


def test_get_kp_catalog_service_reload_on_mtime(tmp_path: Path) -> None:
    cat_path = tmp_path / "kp_catalog.json"
    payload = {
        "schema_version": "1.0.0",
        "school_stage": "primary",
        "units": [
            {
                "unit_id": "u1",
                "grade": 2,
                "subject": "数学",
                "unit_title": "单元一",
                "knowledge_points": [
                    {"knowledge_point_id": "kp-a", "title": "A"}
                ],
            }
        ],
    }
    cat_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    invalidate_kp_catalog_cache()

    svc1 = get_kp_catalog_service(catalog_path=cat_path)
    assert len(svc1.catalog.units) == 1
    assert svc1.catalog.units[0].knowledge_points[0].title == "A"

    payload["units"][0]["knowledge_points"][0]["title"] = "A-更新"
    time.sleep(0.05)
    cat_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    svc2 = get_kp_catalog_service(catalog_path=cat_path)
    assert svc2.catalog.units[0].knowledge_points[0].title == "A-更新"


def test_bootstrap_report_shape() -> None:
    report = ensure_family_alpha_content()
    d = report.to_dict()
    assert "question_count" in d
    assert "catalog_units" in d
    assert d["catalog_units"] >= 1
