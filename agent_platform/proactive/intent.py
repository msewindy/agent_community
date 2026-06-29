"""User message intent helpers — work report / dismiss (M5 D3/D4)."""

from __future__ import annotations

import re

_WORK_PATTERNS = (
    re.compile(r"连续(?:工作|干活|做了)?\s*(\d+(?:\.\d+)?)\s*(?:个)?小时"),
    re.compile(r"已经(?:工作|干了|做了)\s*(\d+(?:\.\d+)?)\s*(?:个)?小时"),
    re.compile(r"工作了\s*(\d+(?:\.\d+)?)\s*(?:个)?小时"),
    re.compile(r"(\d+(?:\.\d+)?)\s*(?:个)?小时(?:了|啦)?"),
    re.compile(r"worked\s+for\s+(\d+(?:\.\d+)?)\s*hours?", re.I),
)


def parse_work_minutes_from_text(text: str) -> float | None:
    """Extract reported work duration in minutes from user utterance."""
    t = (text or "").strip()
    if not t:
        return None
    for pat in _WORK_PATTERNS:
        m = pat.search(t)
        if m:
            hours = float(m.group(1))
            if 0.5 <= hours <= 24:
                return hours * 60.0
    return None
