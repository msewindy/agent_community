"""In-memory adapter for CI and offline dev — not a production truth source."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

from agent_platform.memory.contracts import (
    MemoryCategory,
    MemoryCorrectRequest,
    MemoryHit,
    MemoryPort,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStatus,
    MemoryWriteRequest,
)
from agent_platform.memory.gate import content_hash


def _query_tokens(query: str) -> list[str]:
    import re

    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower().strip())
    return [t for t in tokens if len(t) >= 2]


def _match_score(content: str, query: str) -> float | None:
    """Return relevance score, or None if query does not match content."""
    text = content.lower()
    q = query.lower().strip()
    if not q:
        return 0.8
    if q in text:
        return 1.0 if text.startswith(q) else 0.9
    tokens = _query_tokens(q)
    if not tokens:
        return None
    matched = [t for t in tokens if t in text]
    if not matched:
        return None
    if len(matched) == len(tokens):
        return 0.85
    return 0.8


class MockMemAdapter:
    """MemoryPort implementation backed by an in-process dict.

    Features for CI / US-3 rehearsal:
    - ``device_id`` + ``content_hash`` dedup (active records only)
    - tombstone + ``supersedes`` link on ``correct`` with replacement
    - search/list sorted by ``ts`` descending
    """

    def __init__(self, *, dedup: bool = True, persist_path: Optional[str | Path] = None) -> None:
        self._persist_path = Path(persist_path) if persist_path else None
        self._store: dict[str, MemoryRecord] = {}
        self._dedup = dedup
        if self._persist_path and self._persist_path.is_file():
            self._load()

    def _load(self) -> None:
        if not self._persist_path:
            return
        raw = json.loads(self._persist_path.read_text(encoding="utf-8"))
        for item in raw.get("records", []):
            rec = MemoryRecord.model_validate(item)
            self._store[rec.record_id] = rec

    def _flush(self) -> None:
        if not self._persist_path:
            return
        self._persist_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"records": [r.model_dump(mode="json") for r in self._store.values()]}
        self._persist_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    # --- MemoryPort ---

    def write(self, req: MemoryWriteRequest) -> MemoryRecord:
        digest = content_hash(req.content)
        if self._dedup:
            for rec in self._store.values():
                if (
                    rec.status == MemoryStatus.active
                    and rec.device_id == req.device_id
                    and rec.content_hash == digest
                ):
                    return rec

        record = MemoryRecord.from_write_request(req)
        record.content_hash = digest
        self._store[record.record_id] = record
        self._flush()
        return record

    def search(self, req: MemorySearchRequest) -> MemorySearchResult:
        q = req.query.strip()
        hits: list[MemoryHit] = []
        for rec in self._store.values():
            if rec.status != MemoryStatus.active:
                continue
            if req.device_id and rec.device_id != req.device_id:
                continue
            if req.category and rec.category != req.category:
                continue
            score = _match_score(rec.content, q)
            if score is None:
                continue
            hits.append(
                MemoryHit(
                    record_id=rec.record_id,
                    content=rec.content,
                    score=score,
                    device_id=rec.device_id,
                    category=rec.category,
                    kind=rec.kind,
                    ts=rec.ts,
                    metadata=rec.metadata,
                )
            )
        hits.sort(key=lambda h: (h.score, h.ts.isoformat() if h.ts else ""), reverse=True)
        return MemorySearchResult(hits=hits[: req.limit])

    def correct(self, req: MemoryCorrectRequest) -> MemoryRecord:
        old = self._store.get(req.record_id)
        if old is None:
            raise KeyError(f"record not found: {req.record_id}")

        if req.replacement:
            new_rec = self.write(req.replacement)
            tomb = old.as_superseded_by(new_rec.record_id)
            tomb.metadata = {**tomb.metadata, "correct_reason": req.reason}
            self._store[old.record_id] = tomb
            self._flush()
            return new_rec

        tomb = old.as_tombstone(reason=req.reason)
        self._store[old.record_id] = tomb
        self._flush()
        return tomb

    def list_records(
        self,
        *,
        device_id: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        rows = [
            r
            for r in self._store.values()
            if r.status == MemoryStatus.active
            and (device_id is None or r.device_id == device_id)
            and (category is None or r.category == category)
        ]
        rows.sort(key=lambda r: r.ts, reverse=True)
        return rows[:limit]

    # --- test / panel helpers (not on MemoryPort) ---

    def get(self, record_id: str) -> Optional[MemoryRecord]:
        return self._store.get(record_id)

    def clear(self) -> None:
        self._store.clear()

    def all_records(self, *, include_tombstoned: bool = True) -> list[MemoryRecord]:
        rows = list(self._store.values())
        if not include_tombstoned:
            rows = [r for r in rows if r.status == MemoryStatus.active]
        rows.sort(key=lambda r: r.ts, reverse=True)
        return rows


def assert_implements_memory_port(adapter: object) -> None:
    """Runtime check used in tests — both adapters must satisfy MemoryPort."""
    assert isinstance(adapter, MemoryPort), f"{type(adapter)} does not implement MemoryPort"
