#!/usr/bin/env python3
"""Migrate legacy question-only ingest jobs → question inbox; archive job files."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_platform.learning.kp_document_parser import KpDocumentDraft  # noqa: E402
from agent_platform.learning.question_inbox import QuestionInboxService  # noqa: E402
from agent_platform.learning.question_pending_review import is_question_bank_queue  # noqa: E402
from agent_platform.learning.textbook_ingest import TextbookIngestService  # noqa: E402


def main() -> int:
    ingest = TextbookIngestService()
    inbox = QuestionInboxService()
    jobs_dir = ingest.jobs_dir
    archive = jobs_dir / "_migrated_to_inbox"
    archive.mkdir(parents=True, exist_ok=True)

    migrated_questions = 0
    archived_jobs: list[str] = []

    for path in sorted(jobs_dir.glob("ing-*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        job_id = raw.get("job_id", path.stem)
        if not raw.get("parsed_draft"):
            continue
        from agent_platform.learning.textbook_ingest import TextbookIngestJob

        job = TextbookIngestJob.model_validate(raw)
        if not is_question_bank_queue(job):
            print(f"skip (KP job): {job_id} status={job.status.value}")
            continue

        draft = KpDocumentDraft.model_validate(job.parsed_draft)
        added = inbox.upsert_from_draft(draft, source_ref=job.source_path)
        migrated_questions += len(added)
        dest = archive / path.name
        shutil.move(str(path), str(dest))
        archived_jobs.append(job_id)
        print(f"migrated {job_id}: +{len(added)} questions → inbox, archived job file")

    pending = inbox.list_pending()
    print(json.dumps({
        "archived_jobs": archived_jobs,
        "inbox_pending": len(pending),
        "migrated_questions_this_run": migrated_questions,
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
