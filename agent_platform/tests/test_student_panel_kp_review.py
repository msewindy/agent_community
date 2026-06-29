"""P1-C — Web KP ingest review panel APIs."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from agent_platform.api.student_panel import _display_source, create_app
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_ingest_review import KpIngestReviewService, ResolutionAction
from agent_platform.learning.textbook_ingest import (
    IngestJobStatus,
    IngestSourceType,
    TextbookIngestJob,
    TextbookIngestService,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
MATH_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


@pytest.fixture
def review_client(tmp_path: Path) -> tuple[TestClient, TextbookIngestService, KpCatalogService]:
    data = tmp_path / "student_data"
    ingest = TextbookIngestService(data_root=data)
    catalog_path = tmp_path / "kp_catalog.json"
    catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")
    catalog = KpCatalogService(catalog_path=catalog_path)
    review = KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)
    cfg = {
        "data": {"root": str(data)},
        "web_panel": {"port": 8770},
        "pilot": {"grade_level": 2},
    }
    client = TestClient(
        create_app(
            config=cfg,
            catalog_svc=catalog,
            ingest_svc=ingest,
            review_svc=review,
        )
    )
    return client, ingest, catalog


def test_kp_review_page_and_catalog_tree(review_client) -> None:
    client, _, _ = review_client
    page = client.get("/kp-review")
    assert page.status_code == 200
    assert "知识点入库" in page.text
    assert "新建提交" in page.text
    assert "浏览知识库" in page.text
    assert "家长学情" not in page.text

    catalog_page = client.get("/kp-catalog")
    assert catalog_page.status_code == 200
    assert "知识点库" in catalog_page.text
    assert "结构树" in catalog_page.text

    info = client.get("/api/kp/catalog/info")
    assert info.status_code == 200
    info_body = info.json()
    assert info_body["unit_count"] >= 1
    assert info_body["knowledge_point_count"] >= 1
    assert "数学" in info_body["subjects"] or "语文" in info_body["subjects"]

    tree = client.get("/api/kp/catalog/tree")
    assert tree.status_code == 200
    payload = tree.json()
    assert payload["subjects"]
    math = next(s for s in payload["subjects"] if s["subject"] == "数学")
    assert math["grades"][0]["units"]


def test_catalog_tree_filter_by_subject(review_client) -> None:
    client, _, _ = review_client
    tree = client.get("/api/kp/catalog/tree", params={"subject": "语文", "grade": 2})
    assert tree.status_code == 200
    payload = tree.json()
    assert len(payload["subjects"]) == 1
    assert payload["subjects"][0]["subject"] == "语文"
    units = payload["subjects"][0]["grades"][0]["units"]
    assert any(u["unit_id"] == "chinese-g2-sentence-basic" for u in units)


def test_review_resolve_and_approve_via_api(review_client) -> None:
    client, ingest, catalog = review_client
    job = ingest.submit_kp_document(CHINESE_SAMPLE)

    listed = client.get("/api/kp/ingest/jobs?status=pending_review")
    assert listed.status_code == 200
    assert any(item["job_id"] == job.job_id for item in listed.json())

    review = client.get(f"/api/kp/ingest/jobs/{job.job_id}/review")
    assert review.status_code == 200
    body = review.json()
    assert body["blocking_unresolved"] > 0
    assert body["format_validation"]

    for conflict in body["conflicts"]:
        if not conflict["blocking"]:
            continue
        if conflict["resolution"]:
            continue
        action = conflict["allowed_actions"][0]
        payload = {"conflict_id": conflict["conflict_id"], "action": action}
        if action == ResolutionAction.rename_draft.value:
            payload["new_knowledge_point_id"] = f"{conflict['knowledge_point_id']}-web"
        res = client.post(f"/api/kp/ingest/jobs/{job.job_id}/resolve", json=payload)
        assert res.status_code == 200, res.text

    review2 = client.get(f"/api/kp/ingest/jobs/{job.job_id}/review")
    assert review2.json()["ready_to_approve"] is True

    approved = client.post(f"/api/kp/ingest/jobs/{job.job_id}/approve")
    assert approved.status_code == 200
    assert Path(approved.json()["backup_path"]).is_file()

    updated = catalog._path.read_text(encoding="utf-8")  # noqa: SLF001
    assert "kp-g2-punct-exclaim" in updated

    job2 = ingest.get_job(job.job_id)
    assert job2.status == IngestJobStatus.approved


def test_approve_before_ready_returns_400(review_client) -> None:
    client, ingest, _ = review_client
    job = ingest.submit_kp_document(CHINESE_SAMPLE)
    res = client.post(f"/api/kp/ingest/jobs/{job.job_id}/approve")
    assert res.status_code == 400


def test_reject_job(review_client) -> None:
    client, ingest, catalog = review_client
    job = ingest.submit_kp_document(MATH_SAMPLE)
    before = catalog._path.read_text(encoding="utf-8")  # noqa: SLF001
    res = client.post(f"/api/kp/ingest/jobs/{job.job_id}/reject", json={"reason": "web test"})
    assert res.status_code == 200
    assert res.json()["status"] == IngestJobStatus.rejected.value
    assert catalog._path.read_text(encoding="utf-8") == before  # noqa: SLF001


def test_list_jobs_includes_all_statuses(review_client) -> None:
    client, ingest, _ = review_client
    job = ingest.submit_kp_document(MATH_SAMPLE)
    listed = client.get("/api/kp/ingest/jobs")
    assert listed.status_code == 200
    items = listed.json()
    assert any(i["job_id"] == job.job_id and i["status"] == "pending_review" for i in items)
    assert all("status_label" in i and "source_filename" in i for i in items)


def test_submit_sample_via_api(review_client) -> None:
    client, ingest, _ = review_client
    res = client.post("/api/kp/ingest/submit-sample", json={"sample_id": "math-g2"})
    assert res.status_code == 200, res.text
    job_id = res.json()["job"]["job_id"]
    job = ingest.get_job(job_id)
    assert job.status == IngestJobStatus.pending_review
    assert job.parsed_draft is not None


def test_submit_upload_via_api(review_client) -> None:
    client, ingest, _ = review_client
    content = MATH_SAMPLE.read_bytes()
    res = client.post(
        "/api/kp/ingest/submit",
        files={"file": ("数学-二年级.kp.md", content, "text/markdown")},
    )
    assert res.status_code == 200, res.text
    job_id = res.json()["job"]["job_id"]
    job = ingest.get_job(job_id)
    assert job.status == IngestJobStatus.pending_review
    assert "_kp_uploads" in job.source_path


def test_display_path_infers_docs_content_for_legacy_upload() -> None:
    storage = REPO_ROOT / "student_data" / "_kp_uploads" / "20260619-104844-语文-二年级.kp.md"
    job = TextbookIngestJob(
        job_id="ing-test",
        source_type=IngestSourceType.kp_doc,
        source_path=str(storage),
        status=IngestJobStatus.pending_review,
        created_at="2026-06-19T10:48:44+00:00",
    )
    source = _display_source(job)
    assert source["display_path"] == "docs/content/语文-二年级.kp.md"
