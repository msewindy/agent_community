"""P1-E — merge approved draft into kp_catalog.json."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_catalog_merge import KpCatalogWriter
from agent_platform.learning.kp_ingest_review import KpIngestReviewService, ResolutionAction
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestService

REPO_ROOT = Path(__file__).resolve().parents[2]
MATH_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def merge_env(tmp_path: Path):
    data = tmp_path / "student_data"
    ingest = TextbookIngestService(data_root=data)
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    review = KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)
    return review, ingest, catalog, data


def _resolve_all_conflicts(review: KpIngestReviewService, job_id: str) -> None:
    job = review._ingest.get_job(job_id)  # noqa: SLF001
    snapshot = review.build_snapshot(job)
    for conflict in snapshot.catalog_diff.conflicts:
        if conflict.kind.value == "subject_grade_mismatch":
            continue
        if conflict.kind.value == "kp_title_mismatch":
            review.set_resolution(job_id, conflict.conflict_id, ResolutionAction.use_draft)
        elif conflict.kind.value == "kp_missing_in_draft":
            review.set_resolution(job_id, conflict.conflict_id, ResolutionAction.use_catalog)
        elif conflict.kind.value == "kp_cross_unit":
            review.set_resolution(
                job_id,
                conflict.conflict_id,
                ResolutionAction.rename_draft,
                new_knowledge_point_id=f"{conflict.knowledge_point_id}-draft",
            )


def test_merge_adds_new_unit_and_updates_existing(merge_env) -> None:
    review, ingest, catalog, _data = merge_env
    job = ingest.submit_kp_document(MATH_SAMPLE)
    _resolve_all_conflicts(review, job.job_id)

    result = review.approve(job.job_id)
    assert Path(result.backup_path).is_file()
    assert Path(result.audit_path).is_file()
    assert result.merge_report.units_updated or result.merge_report.units_added

    updated = json.loads(catalog._path.read_text(encoding="utf-8"))  # noqa: SLF001
    math_unit = next(u for u in updated["units"] if u["unit_id"] == "math-g2-add-sub-100")
    assert len(math_unit["knowledge_points"]) >= 8

    job2 = ingest.get_job(job.job_id)
    assert job2.status == IngestJobStatus.approved
    assert job2.approved_at
    assert job2.catalog_backup_path == result.backup_path


def test_approve_not_ready_raises(merge_env) -> None:
    review, ingest, _, _ = merge_env
    job = ingest.submit_kp_document(CHINESE_SAMPLE)
    with pytest.raises(ValueError, match="not ready_to_approve"):
        review.approve(job.job_id)


def test_reject_does_not_touch_catalog(merge_env) -> None:
    review, ingest, catalog, _ = merge_env
    job = ingest.submit_kp_document(MATH_SAMPLE)
    before = catalog._path.read_text(encoding="utf-8")  # noqa: SLF001
    rejected = review.reject(job.job_id, reason="test")
    assert rejected.status == IngestJobStatus.rejected
    assert catalog._path.read_text(encoding="utf-8") == before  # noqa: SLF001


def test_save_with_backup_rotates_catalog(merge_env) -> None:
    _review, _ingest, catalog, data = merge_env
    writer = KpCatalogWriter(catalog, audit_dir=data / "_kp_catalog_audit")
    original_units = len(catalog.catalog.units)
    backup = writer.save_with_backup(catalog.catalog)
    assert backup.is_file()
    reloaded = KpCatalogService(catalog_path=catalog._path)  # noqa: SLF001
    assert len(reloaded.catalog.units) == original_units
