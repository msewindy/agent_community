#!/usr/bin/env python3
"""Merge duplicate textbook question-pending jobs and tag legacy batches."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_platform.learning.question_pending_review import (  # noqa: E402
    dedupe_question_pending_jobs,
    list_question_pending_jobs,
)
from agent_platform.learning.textbook_ingest import TextbookIngestService


def main() -> int:
    ingest = TextbookIngestService()
    before = list_question_pending_jobs(ingest)
    print(f"pending question jobs before: {len(before)}")
    for job in before:
        print(f"  - {job.job_id}  {Path(job.source_path).name}  status={job.status.value}")

    report = dedupe_question_pending_jobs(ingest)
    print(json.dumps(report, ensure_ascii=False, indent=2))

    after = list_question_pending_jobs(ingest)
    print(f"pending question jobs after: {len(after)}")
    for job in after:
        qn = sum(len(u.get("questions") or []) for u in (job.parsed_draft or {}).get("units") or [])
        print(f"  - {job.job_id}  questions={qn}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
