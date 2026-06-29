#!/usr/bin/env python3
"""Check M8 seven-day diary completion from markdown checkboxes."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path


def parse_diary(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    days = re.findall(r"^## Day (\d+).*$", text, re.MULTILINE)
    checked = len(re.findall(r"- \[x\]", text, re.IGNORECASE))
    unchecked = len(re.findall(r"- \[ \]", text))
    voice_hits = re.findall(r"语音交互次数[：:]\s*(\d+)", text)
    voice_total = sum(int(x) for x in voice_hits)
    return {
        "days_marked": len(days),
        "checked": checked,
        "unchecked": unchecked,
        "voice_total": voice_total,
        "path": str(path),
    }


def main() -> int:
    p = argparse.ArgumentParser(description="M8 seven-day diary checker")
    p.add_argument(
        "diary",
        nargs="?",
        default="docs/M8-seven-day-diary.md",
        type=Path,
    )
    p.add_argument("--min-days", type=int, default=7)
    p.add_argument("--min-voice-per-day", type=int, default=5)
    args = p.parse_args()

    if not args.diary.is_file():
        print(f"diary not found: {args.diary}", file=sys.stderr)
        print("Copy docs/M8-seven-day-diary.md and fill daily entries.")
        return 2

    stats = parse_diary(args.diary)
    print(f"diary: {stats['path']}")
    print(f"days sections: {stats['days_marked']}")
    print(f"checkboxes: {stats['checked']} done / {stats['unchecked']} open")
    print(f"voice interactions logged: {stats['voice_total']}")

    if stats["days_marked"] < args.min_days:
        print(f"INCOMPLETE: need {args.min_days} day sections", file=sys.stderr)
        return 1
    if stats["unchecked"] > 0:
        print("INCOMPLETE: unchecked items remain", file=sys.stderr)
        return 1

    print("diary_check: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
