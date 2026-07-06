"""Map primary subject labels to pilot unit_id keys in config."""

from __future__ import annotations

from typing import Optional

_PILOT_KEYS: dict[str, str] = {
    "数学": "math",
    "语文": "chinese",
    "英语": "english",
}


def pilot_unit_id(units: dict, primary_subject: str) -> Optional[str]:
    """Resolve configured pilot unit for a subject (数学 / 语文 / 英语)."""
    key = _PILOT_KEYS.get(primary_subject.strip())
    if key:
        uid = units.get(key)
        if uid:
            return str(uid)
    return None
