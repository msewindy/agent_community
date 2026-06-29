#!/usr/bin/env python3
"""P1 acceptance — `.kp.md` submit → review → approve → catalog merge."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_ingest_review import KpIngestReviewService, ResolutionAction
from agent_platform.learning.textbook_ingest import IngestJobStatus, TextbookIngestService

REPO_ROOT = Path(__file__).resolve().parents[2]
MATH_SAMPLE = REPO_ROOT / "docs" / "content" / "数学-二年级.kp.md"
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def _resolve_all(review: KpIngestReviewService, job_id: str) -> None:
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


def accept_kp_document_ingest() -> int:
    if not MATH_SAMPLE.is_file():
        return _fail(f"missing sample: {MATH_SAMPLE}")

    with tempfile.TemporaryDirectory(prefix="kp-ingest-accept-") as td:
        root = Path(td) / "student_data"
        catalog_path = Path(td) / "kp_catalog.json"
        catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")

        ingest = TextbookIngestService(data_root=root)
        catalog = KpCatalogService(catalog_path=catalog_path)
        review = KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)

        job = ingest.submit_kp_document(MATH_SAMPLE)
        if job.status != IngestJobStatus.pending_review:
            return _fail(f"submit status={job.status}")
        if not job.catalog_diff:
            return _fail("submit missing catalog_diff")

        snap = review.build_snapshot(job)
        if snap.blocking_unresolved == 0:
            return _fail("expected conflicts for math sample")

        _resolve_all(review, job.job_id)
        job2 = review.refresh_job_review(job.job_id)
        snap2 = review.build_snapshot(job2)
        if not snap2.ready_to_approve:
            return _fail(f"not ready: blocking={snap2.blocking_unresolved}")

        result = review.approve(job.job_id)
        if not Path(result.backup_path).is_file():
            return _fail("backup missing")
        if not Path(result.audit_path).is_file():
            return _fail("audit missing")

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        unit_ids = {u["unit_id"] for u in payload["units"]}
        if "math-g2-multiply-table-2-5" not in unit_ids:
            return _fail("new unit not merged")

        math = next(u for u in payload["units"] if u["unit_id"] == "math-g2-add-sub-100")
        if len(math["knowledge_points"]) < 8:
            return _fail(f"math unit kp count={len(math['knowledge_points'])}")

        approved = ingest.get_job(job.job_id)
        if approved.status != IngestJobStatus.approved:
            return _fail(f"job status={approved.status}")

        _ok(f"approve job={job.job_id} backup={Path(result.backup_path).name}")
        _ok(f"units_added={result.merge_report.units_added}")
        _ok(f"audit={Path(result.audit_path).name}")

    return 0


if __name__ == "__main__":
    sys.exit(accept_kp_document_ingest())
