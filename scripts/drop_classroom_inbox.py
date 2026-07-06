#!/usr/bin/env python3
"""Drop classroom-only placeholder rows from question inbox (family Alpha)."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from agent_platform.learning.question_inbox import QuestionInboxService  # noqa: E402


def main() -> int:
    svc = QuestionInboxService()
    before = len(svc.list_pending())
    dropped = svc.drop_classroom_placeholders()
    after = len(svc.list_pending())
    print(f"pending before: {before}")
    print(f"dropped placeholders: {dropped}")
    print(f"pending after: {after}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
