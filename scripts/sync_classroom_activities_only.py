#!/usr/bin/env python3
"""仅同步沪教三年级课本课堂活动清单 + reading KP Wiki 说明（不改 catalog / 题库）。"""

from __future__ import annotations

import argparse
import hashlib
import json
import sqlite3
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agent_platform.learning.hujiao_g3_english_ingest import run_classroom_activities_sync_only
from agent_platform.learning.kp_catalog import get_kp_catalog_service
from agent_platform.learning.question_bank import QuestionBankService


def _catalog_fingerprint() -> str:
    svc = get_kp_catalog_service()
    payload = svc.catalog.model_dump(mode="json")
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]


def _question_count() -> int:
    bank = QuestionBankService()
    if not bank.sqlite_path.is_file():
        return 0
    with sqlite3.connect(bank.sqlite_path) as conn:
        return int(conn.execute("SELECT COUNT(*) FROM questions").fetchone()[0])


def main() -> int:
    parser = argparse.ArgumentParser(description="仅同步课堂活动清单与 reading Wiki")
    parser.add_argument("--summary", type=Path, help="词句汇总 PDF 路径")
    parser.add_argument("--textbook", type=Path, help="课本 PDF 路径")
    parser.add_argument("--no-wiki", action="store_true", help="只写 classroom_activities.json，不更新 Wiki")
    args = parser.parse_args()

    before_cat = _catalog_fingerprint()
    before_q = _question_count()

    report = run_classroom_activities_sync_only(
        summary_path=args.summary,
        textbook_path=args.textbook,
        patch_wiki=not args.no_wiki,
    )

    after_cat = _catalog_fingerprint()
    after_q = _question_count()
    out = report.to_dict()
    out["verify"] = {
        "catalog_unchanged": before_cat == after_cat,
        "question_count_before": before_q,
        "question_count_after": after_q,
        "questions_unchanged": before_q == after_q,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))

    if before_cat != after_cat or before_q != after_q:
        print("WARNING: catalog 或题库题量发生变化，请人工核对", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
