#!/usr/bin/env python3
"""Full KP ingest walkthrough — 数学 + 语文 .kp.md → approve → catalog（隔离临时目录）."""

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
CHINESE_SAMPLE = REPO_ROOT / "docs" / "content" / "语文-二年级.kp.md"
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


def _ingest_and_approve(
    *,
    review: KpIngestReviewService,
    ingest: TextbookIngestService,
    catalog_path: Path,
    sample: Path,
    label: str,
    verify_fn,
) -> int | None:
    if not sample.is_file():
        return _fail(f"missing sample: {sample}")

    job = ingest.submit_kp_document(sample)
    if job.status != IngestJobStatus.pending_review:
        return _fail(f"{label} submit status={job.status}")
    if not job.catalog_diff:
        return _fail(f"{label} missing catalog_diff")

    snap = review.build_snapshot(job)
    _ok(f"{label} submit job={job.job_id} conflicts={len(snap.catalog_diff.conflicts)} blocking={snap.blocking_unresolved}")

    _resolve_all(review, job.job_id)
    snap2 = review.build_snapshot(review.refresh_job_review(job.job_id))
    if not snap2.ready_to_approve:
        return _fail(f"{label} not ready_to_approve blocking={snap2.blocking_unresolved}")

    result = review.approve(job.job_id)
    if not Path(result.backup_path).is_file():
        return _fail(f"{label} backup missing")
    if not Path(result.audit_path).is_file():
        return _fail(f"{label} audit missing")

    payload = json.loads(catalog_path.read_text(encoding="utf-8"))
    err = verify_fn(payload, result)
    if err:
        return _fail(f"{label} {err}")

    approved = ingest.get_job(job.job_id)
    if approved.status != IngestJobStatus.approved:
        return _fail(f"{label} job status={approved.status}")

    _ok(
        f"{label} approve units_added={result.merge_report.units_added} "
        f"units_updated={result.merge_report.units_updated} "
        f"kp+{result.merge_report.knowledge_points_added}"
    )
    return None


def _verify_math(payload: dict, result) -> str | None:
    del result
    unit_ids = {u["unit_id"] for u in payload["units"]}
    if "math-g2-multiply-table-2-5" not in unit_ids:
        return "math new unit missing"
    math = next(u for u in payload["units"] if u["unit_id"] == "math-g2-add-sub-100")
    if len(math["knowledge_points"]) < 8:
        return f"math kp count={len(math['knowledge_points'])}"
    return None


def _verify_chinese(payload: dict, result) -> str | None:
    del result
    unit_ids = {u["unit_id"] for u in payload["units"]}
    if "chinese-g2-words-collocation" not in unit_ids:
        return "chinese new unit missing"
    basic = next(u for u in payload["units"] if u["unit_id"] == "chinese-g2-sentence-basic")
    kp_ids = {kp["knowledge_point_id"] for kp in basic["knowledge_points"]}
    expected = {
        "kp-g2-punct-period",
        "kp-g2-punct-question",
        "kp-g2-punct-exclaim",
        "kp-g2-punct-comma",
        "kp-g2-word-order",
        "kp-g2-sentence-complete",
    }
    missing = expected - kp_ids
    if missing:
        return f"chinese basic unit missing kp: {sorted(missing)}"
    words = next(u for u in payload["units"] if u["unit_id"] == "chinese-g2-words-collocation")
    if len(words["knowledge_points"]) < 5:
        return f"words unit kp count={len(words['knowledge_points'])}"
    return None


def accept_kp_full_ingest() -> int:
    print("accept_kp_full_ingest: 数学 → 语文 顺序入库（临时 catalog，不改生产文件）")
    print("-" * 60)

    with tempfile.TemporaryDirectory(prefix="kp-full-ingest-") as td:
        root = Path(td) / "student_data"
        catalog_path = Path(td) / "kp_catalog.json"
        catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")

        ingest = TextbookIngestService(data_root=root)
        catalog = KpCatalogService(catalog_path=catalog_path)
        review = KpIngestReviewService(ingest_svc=ingest, catalog_svc=catalog)

        err = _ingest_and_approve(
            review=review,
            ingest=ingest,
            catalog_path=catalog_path,
            sample=MATH_SAMPLE,
            label="数学",
            verify_fn=_verify_math,
        )
        if err:
            return err

        err = _ingest_and_approve(
            review=review,
            ingest=ingest,
            catalog_path=catalog_path,
            sample=CHINESE_SAMPLE,
            label="语文",
            verify_fn=_verify_chinese,
        )
        if err:
            return err

        final = json.loads(catalog_path.read_text(encoding="utf-8"))
        subjects = {u["subject"] for u in final["units"]}
        if subjects != {"数学", "语文"}:
            return _fail(f"unexpected subjects: {subjects}")

        _ok(f"final catalog units={len(final['units'])} path={catalog_path}")
        _ok("数学 + 语文 完整入库链路通过")

    print("-" * 60)
    print("accept_kp_full_ingest: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(accept_kp_full_ingest())
