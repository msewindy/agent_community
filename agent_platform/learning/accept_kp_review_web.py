#!/usr/bin/env python3
"""P1 Web E2E — submit(页面 API) → review → resolve → approve（数学 + 语文）."""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

from fastapi.testclient import TestClient

from agent_platform.api.student_panel import create_app
from agent_platform.learning.kp_catalog import KpCatalogService
from agent_platform.learning.kp_ingest_review import ResolutionAction
from agent_platform.learning.textbook_ingest import TextbookIngestService

REPO_ROOT = Path(__file__).resolve().parents[2]
SEED_CATALOG = REPO_ROOT / "agent_platform" / "learning" / "catalog" / "kp_catalog.json"


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> int:
    print(f"FAIL {msg}", file=sys.stderr)
    return 1


def _web_submit_sample(client: TestClient, sample_id: str) -> str | None:
    res = client.post("/api/kp/ingest/submit-sample", json={"sample_id": sample_id})
    if res.status_code != 200:
        return _fail(f"submit-sample {sample_id}: {res.text}")
    return res.json()["job"]["job_id"]


def _web_review_flow(client: TestClient, job_id: str, label: str) -> int | None:
    rev = client.get(f"/api/kp/ingest/jobs/{job_id}/review")
    if rev.status_code != 200:
        return _fail(f"{label} review: {rev.text}")

    for conflict in rev.json()["conflicts"]:
        if not conflict["blocking"] or conflict["resolution"]:
            continue
        action = conflict["allowed_actions"][0]
        payload = {"conflict_id": conflict["conflict_id"], "action": action}
        if action == ResolutionAction.rename_draft.value:
            payload["new_knowledge_point_id"] = f"{conflict['knowledge_point_id']}-web"
        if client.post(f"/api/kp/ingest/jobs/{job_id}/resolve", json=payload).status_code != 200:
            return _fail(f"{label} resolve")

    if not client.get(f"/api/kp/ingest/jobs/{job_id}/review").json()["ready_to_approve"]:
        return _fail(f"{label} not ready_to_approve")

    approved = client.post(f"/api/kp/ingest/jobs/{job_id}/approve")
    if approved.status_code != 200:
        return _fail(f"{label} approve: {approved.text}")

    _ok(f"{label} web E2E approve job={job_id}")
    return None


def accept_kp_review_web() -> int:
    print("accept_kp_review_web: 页面 API 端到端（submit-sample → approve）")
    print("-" * 60)

    with tempfile.TemporaryDirectory(prefix="kp-review-web-") as td:
        root = Path(td) / "student_data"
        catalog_path = Path(td) / "kp_catalog.json"
        catalog_path.write_text(SEED_CATALOG.read_text(encoding="utf-8"), encoding="utf-8")

        ingest = TextbookIngestService(data_root=root)
        catalog = KpCatalogService(catalog_path=catalog_path)
        cfg = {"data": {"root": str(root)}, "web_panel": {"port": 8770}, "pilot": {"grade_level": 2}}
        client = TestClient(create_app(config=cfg, catalog_svc=catalog, ingest_svc=ingest))

        page = client.get("/kp-review")
        if page.status_code != 200 or "新建提交" not in page.text:
            return _fail("kp-review page missing upload UI")

        math_job = _web_submit_sample(client, "math-g2")
        if isinstance(math_job, int):
            return math_job
        err = _web_review_flow(client, math_job, "数学")
        if err:
            return err

        chinese_job = _web_submit_sample(client, "chinese-g2")
        if isinstance(chinese_job, int):
            return chinese_job
        err = _web_review_flow(client, chinese_job, "语文")
        if err:
            return err

        payload = json.loads(catalog_path.read_text(encoding="utf-8"))
        unit_ids = {u["unit_id"] for u in payload["units"]}
        expected = {
            "math-g2-add-sub-100",
            "math-g2-multiply-table-2-5",
            "chinese-g2-sentence-basic",
            "chinese-g2-words-collocation",
        }
        if not expected.issubset(unit_ids):
            return _fail(f"catalog units missing: {expected - unit_ids}")

        _ok(f"final catalog units={len(payload['units'])}")

    print("-" * 60)
    print("accept_kp_review_web: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(accept_kp_review_web())
