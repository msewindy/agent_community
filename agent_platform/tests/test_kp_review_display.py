"""Tests for kp_review_display."""

from __future__ import annotations

from pathlib import Path

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_document_parser import parse_kp_document
from agent_platform.learning.kp_ingest_review import KpIngestReviewService
from agent_platform.learning.kp_review_display import build_document_tree, build_kb_comparison

REPO_ROOT = Path(__file__).resolve().parents[2]
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"


def test_build_document_tree_from_draft() -> None:
    draft = parse_kp_document(CHINESE_SAMPLE)
    tree = build_document_tree(draft.model_dump(mode="json"))
    assert len(tree) == 2
    assert tree[0]["knowledge_points"]
    assert "更新" not in tree[0]["unit_title"]


def test_kb_comparison_has_group_labels() -> None:
    catalog = KpCatalogService()
    draft = parse_kp_document(CHINESE_SAMPLE)
    review = KpIngestReviewService(catalog_svc=catalog)
    from agent_platform.learning.textbook_ingest import IngestJobStatus, IngestSourceType, TextbookIngestJob

    job = TextbookIngestJob(
        job_id="test",
        source_type=IngestSourceType.kp_doc,
        source_path=str(CHINESE_SAMPLE),
        status=IngestJobStatus.pending_review,
        parsed_draft=draft.model_dump(mode="json"),
        created_at="2026-01-01T00:00:00",
    )
    snap = KpIngestReviewService(catalog_svc=catalog).build_snapshot(job)
    kb = build_kb_comparison(snap.catalog_diff, snap.conflict_resolutions)
    labels = [g["label"] for g in kb["groups"]]
    assert any("新增" in label or "已存在" in label or "知识库" in label for label in labels)
    assert "new_units" in kb
    assert "unit_comparisons" not in kb
