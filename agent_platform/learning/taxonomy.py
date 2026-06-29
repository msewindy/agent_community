"""Error taxonomy loader (Phase 3)."""

from __future__ import annotations

import re
from typing import Optional

from agent_platform.learning._config import load_student_learning_config
from agent_platform.learning.contracts import TaxonomyEntry

_GAP_ID_PATTERN = re.compile(r"^gap-[a-z0-9-]+$")


def gap_id_for_error_code(error_code: str) -> str:
    slug = error_code.lower().replace("_", "-")
    gap_id = f"gap-{slug}"
    if not _GAP_ID_PATTERN.match(gap_id):
        raise ValueError(f"invalid gap_id derived from error_code: {error_code}")
    return gap_id


def gap_id_for_kp(knowledge_point_id: str) -> str:
    """知识点为主轴后，gap 主键由知识点派生（一个知识点一条掌握档）。"""
    slug = knowledge_point_id.strip().lower().replace("_", "-")
    gap_id = f"gap-{slug}"
    if not _GAP_ID_PATTERN.match(gap_id):
        raise ValueError(f"invalid gap_id derived from knowledge_point_id: {knowledge_point_id}")
    return gap_id


class TaxonomyService:
    def __init__(self, config: Optional[dict] = None) -> None:
        cfg = config or load_student_learning_config()
        tax = cfg.get("error_taxonomy") or {}
        self._version = str(tax.get("version", "0.0.0"))
        self._entries: dict[str, TaxonomyEntry] = {}
        for code, meta in (tax.get("codes") or {}).items():
            entry = TaxonomyEntry(
                error_code=str(code),
                title=str(meta["title"]),
                knowledge_point_id=str(meta["knowledge_point_id"]),
                gap_id=gap_id_for_error_code(str(code)),
            )
            self._entries[entry.error_code] = entry

    @property
    def version(self) -> str:
        return self._version

    def lookup(self, error_code: str) -> TaxonomyEntry:
        entry = self._entries.get(error_code)
        if entry is None:
            raise KeyError(f"unknown error_code in taxonomy: {error_code}")
        return entry

    def gap_id_for(self, error_code: str) -> str:
        return self.lookup(error_code).gap_id

    def list_codes(self) -> list[str]:
        return sorted(self._entries.keys())
