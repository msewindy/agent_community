"""P1-B — ingest review checklist + resolutions."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_ingest_review import KpIngestReviewService, ResolutionAction
from agent_platform.learning.textbook_ingest import TextbookIngestService

REPO_ROOT = Path(__file__).resolve().parents[2]
MATH_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"


@pytest.fixture
def review_env(tmp_path: Path):
    data = tmp_path / "student_data"
    ingest = TextbookIngestService(data_root=data)
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(
        (REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    catalog = KpCatalogService(catalog_path=catalog_path)
    review = KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)
    return review, ingest


def test_submit_kp_doc_attaches_catalog_diff(review_env) -> None:
    review, ingest = review_env
    job = ingest.submit_kp_document(MATH_SAMPLE)
    assert job.catalog_diff is not None
    assert job.review_checklist
    snapshot = review.build_snapshot(job)
    assert snapshot.ready_to_approve is (snapshot.blocking_unresolved == 0)


def test_resolve_flow_ready_without_manual_flags(review_env) -> None:
    review, ingest = review_env
    job = ingest.submit_kp_document(CHINESE_SAMPLE)
    snapshot = review.build_snapshot(job)
    assert snapshot.blocking_unresolved > 0
    assert all(item.rule_id.startswith("F") for item in snapshot.checklist)

    for conflict in snapshot.catalog_diff.conflicts:
        if conflict.kind.value == "subject_grade_mismatch":
            continue
        if conflict.kind.value == "kp_title_mismatch":
            review.set_resolution(job.job_id, conflict.conflict_id, ResolutionAction.use_draft)
        elif conflict.kind.value == "kp_missing_in_draft":
            review.set_resolution(job.job_id, conflict.conflict_id, ResolutionAction.use_catalog)
        elif conflict.kind.value == "kp_cross_unit":
            review.set_resolution(
                job.job_id,
                conflict.conflict_id,
                ResolutionAction.rename_draft,
                new_knowledge_point_id=f"{conflict.knowledge_point_id}-draft",
            )

    job2 = review.refresh_job_review(job.job_id)
    snap2 = review.build_snapshot(job2)
    assert snap2.blocking_unresolved == 0
    assert snap2.ready_to_approve is True


def test_resolve_invalid_action_raises(review_env) -> None:
    review, ingest = review_env
    job = ingest.submit_kp_document(CHINESE_SAMPLE)
    snapshot = review.build_snapshot(job)
    title_conflict = next(
        c for c in snapshot.catalog_diff.conflicts if c.kind.value == "kp_title_mismatch"
    )
    with pytest.raises(ValueError, match="not allowed"):
        review.set_resolution(job.job_id, title_conflict.conflict_id, ResolutionAction.rename_draft)
