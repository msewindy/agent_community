"""P1-3 — export kp_catalog to editable `.kp.md` drafts."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.student_panel import create_app
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_catalog_export import KpCatalogExportService
from agent_platform.learning.kp_document_parser import parse_kp_document_text
from agent_platform.learning.question_bank import QuestionBankService

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"
G3_SEED = REPO_ROOT / "agent_platform" / "learning" / "question_bank" / "seed_questions_g3_math_hujiao.json"


@pytest.fixture
def catalog(tmp_path: Path) -> KpCatalogService:
    cat_path = tmp_path / "kp_catalog.json"
    cat_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    return KpCatalogService(catalog_path=cat_path)


@pytest.fixture
def bank(tmp_path: Path) -> QuestionBankService:
    return QuestionBankService(seed_path=G3_SEED, sqlite_path=tmp_path / "questions.db")


def test_export_math_grade3_round_trip(catalog: KpCatalogService, bank: QuestionBankService) -> None:
    svc = KpCatalogExportService(catalog=catalog, bank=bank)
    result, draft = svc.export_and_validate(subject="数学", grade=3)
    assert "math-g3-u01" in result.unit_ids
    assert result.knowledge_point_count >= 1
    assert result.question_count >= 1
    assert "## 练习题" in result.content
    assert draft.subject == "数学"
    assert draft.grade == 3
    assert any(u.unit_id == "math-g3-u01" for u in draft.units)
    assert draft.question_count >= 1


def test_export_single_unit_filename(catalog: KpCatalogService, bank: QuestionBankService) -> None:
    svc = KpCatalogExportService(catalog=catalog, bank=bank)
    result = svc.export(subject="数学", grade=3, unit_id="math-g3-u01")
    assert result.filename == "math-g3-u01.kp.md"
    assert result.unit_ids == ["math-g3-u01"]
    assert "unit_id: math-g3-u01" in result.content


def test_export_without_questions(catalog: KpCatalogService, bank: QuestionBankService) -> None:
    svc = KpCatalogExportService(catalog=catalog, bank=bank)
    result = svc.export(
        subject="数学",
        grade=3,
        unit_id="math-g3-u01",
        include_questions=False,
    )
    assert "## 练习题" not in result.content
    assert result.question_count == 0
    draft = parse_kp_document_text(result.content)
    assert draft.question_count == 0


def test_export_unknown_unit_raises(catalog: KpCatalogService, bank: QuestionBankService) -> None:
    svc = KpCatalogExportService(catalog=catalog, bank=bank)
    with pytest.raises(KeyError):
        svc.export(subject="数学", grade=3, unit_id="unit-does-not-exist")


def test_export_api_download(tmp_path: Path) -> None:
    data = tmp_path / "student_data"
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    cfg = {"data": {"root": str(data)}, "web_panel": {"port": 8770}, "pilot": {"grade_level": 3}}
    client = TestClient(create_app(config=cfg, catalog_svc=catalog))

    res = client.get(
        "/api/kp/catalog/export",
        params={
            "subject": "数学",
            "grade": 2,
            "unit_id": "math-g2-add-sub-100",
            "include_questions": "false",
        },
    )
    assert res.status_code == 200, res.text
    assert "math-g2-add-sub-100.kp.md" in res.headers.get("content-disposition", "")
    assert "unit_id: math-g2-add-sub-100" in res.text
    assert "kp-g2-add-carry" in res.text

    full = client.get(
        "/api/kp/catalog/export",
        params={"subject": "数学", "grade": 3, "include_questions": "false"},
    )
    assert full.status_code == 200, full.text
    disp = full.headers.get("content-disposition", "")
    assert "filename*=" in disp
    assert "数学" in disp or "%E6%95%B0%E5%AD%A6" in disp

    page = client.get("/kp-catalog")
    assert page.status_code == 200
    assert "导出草稿" in page.text
    assert "btnExport" in page.text
    assert "btn-export-unit" in page.text

    review = client.get("/kp-review")
    assert review.status_code == 200
    assert "从知识库导出" not in review.text
