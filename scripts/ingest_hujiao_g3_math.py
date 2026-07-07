#!/usr/bin/env python3
"""Ingest 沪教版三年级数学上册 PDF → catalog / wiki / question bank."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

from agent_platform.learning.hujiao_g3_math_ingest import run_hujiao_g3_math_ingest
from agent_platform.learning.hujiao_g3_math_parser import build_kp_document


def main() -> int:
    parser = argparse.ArgumentParser(description="沪教三年级数学上册 PDF 入库")
    parser.add_argument("--textbook", type=Path, help="课本 PDF 路径")
    parser.add_argument("--dry-run", action="store_true", help="仅解析预览，不写 catalog")
    args = parser.parse_args()

    if args.dry_run:
        from agent_platform.learning.hujiao_g3_math_parser import _default_pdf_path
        from agent_platform.learning.g3_textbook_common import pending_exercises

        path = args.textbook or _default_pdf_path()
        draft, exercises = build_kp_document(path)
        preview = {
            "units": len(draft.units),
            "knowledge_points": draft.knowledge_point_count,
            "auto_questions": draft.question_count,
            "classroom_activities": len(pending_exercises(exercises)),
            "unit_ids": [u.unit_id for u in draft.units],
        }
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        return 0

    report = run_hujiao_g3_math_ingest(textbook_path=args.textbook)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
