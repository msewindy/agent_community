"""P0 — TextbookIngestService stub tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_platform.learning.textbook_ingest import (
    IngestJobStatus,
    IngestSourceType,
    TextbookIngestService,
)


@pytest.fixture
def ingest_svc(tmp_path: Path) -> TextbookIngestService:
    return TextbookIngestService(data_root=tmp_path / "student_data")


def test_submit_pdf_creates_pending_job(ingest_svc: TextbookIngestService, tmp_path: Path) -> None:
    sample = tmp_path / "sample.pdf"
    sample.write_bytes(b"%PDF-1.4 stub")

    job = ingest_svc.submit_pdf(sample, subject="数学", grade_level=2)
    assert job.source_type == IngestSourceType.pdf
    assert job.status == IngestJobStatus.pending_review
    assert job.kp_candidates
    assert ingest_svc.get_job(job.job_id).job_id == job.job_id


def test_submit_photo_and_document(ingest_svc: TextbookIngestService, tmp_path: Path) -> None:
    photo = tmp_path / "page.jpg"
    photo.write_bytes(b"\xff\xd8\xff")
    doc = tmp_path / "unit.md"
    doc.write_text("# 二年级句子\n", encoding="utf-8")

    j1 = ingest_svc.submit_photo(photo, subject="语文")
    j2 = ingest_svc.submit_document(doc, subject="语文")
    assert j1.source_type == IngestSourceType.photo
    assert j2.source_type == IngestSourceType.document
    assert len(ingest_svc.list_jobs()) >= 2


def test_submit_missing_file_raises(ingest_svc: TextbookIngestService) -> None:
    with pytest.raises(FileNotFoundError):
        ingest_svc.submit_pdf("/no/such/file.pdf")


def test_get_job_unknown_raises(ingest_svc: TextbookIngestService) -> None:
    with pytest.raises(KeyError):
        ingest_svc.get_job("ing-missing")


def test_submit_kp_doc_parses_real_units(ingest_svc: TextbookIngestService) -> None:
    sample = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"
    job = ingest_svc.submit_kp_document(sample)
    assert job.source_type == IngestSourceType.kp_doc
    assert job.status == IngestJobStatus.pending_review
    assert job.subject == "数学"
    assert job.grade_level == 2
    assert job.parsed_draft is not None
    assert len(job.parsed_draft["units"]) == 2
    assert len(job.kp_candidates) == 12
    assert job.extracted_text_preview.startswith("学科=数学")

    loaded = ingest_svc.get_job(job.job_id)
    assert loaded.parsed_draft["units"][0]["unit_id"] == "math-g2-add-sub-100"


def test_submit_kp_doc_parse_error(ingest_svc: TextbookIngestService, tmp_path: Path) -> None:
    bad = tmp_path / "bad.kp.md"
    bad.write_text("# not a kp doc\n", encoding="utf-8")
    with pytest.raises(ValueError, match="frontmatter"):
        ingest_svc.submit_kp_document(bad)


REPO_ROOT = Path(__file__).resolve().parents[2]
