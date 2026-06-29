"""MemVerse HTTP adapter — maps MemoryPort to /insert and /query (form API)."""

from __future__ import annotations

import json
import re
from typing import Any, Optional
from uuid import uuid4

import httpx

from agent_platform.memory.contracts import (
    MemoryCategory,
    MemoryCorrectRequest,
    MemoryHit,
    MemoryKind,
    MemoryRecord,
    MemorySearchRequest,
    MemorySearchResult,
    MemoryStatus,
    MemoryWriteRequest,
    utc_now,
)
from agent_platform.memory.envelope import decode_envelope, encode_envelope, parse_category
from agent_platform.memory.gate import content_hash

_ERROR_MARKERS = ("⚠️", "LLM generation failed", "RAG retrieval failed", "RAG failed", "invalid_request_error")


def _is_error_text(text: str) -> bool:
    if not text or not text.strip():
        return True
    lower = text.lower()
    return any(m.lower() in lower for m in _ERROR_MARKERS)


class MemVerseAdapter:
    """MemoryPort → MemVerse FastAPI (POST /insert, POST /query)."""

    def __init__(self, base_url: str, timeout_s: float = 180.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_s = timeout_s

    @classmethod
    def from_config(cls, cfg: dict) -> MemVerseAdapter:
        mv = cfg.get("memverse") or {}
        return cls(
            base_url=mv.get("base_url", "http://127.0.0.1:8000"),
            timeout_s=float(mv.get("timeout_s", 180)),
        )

    def _client(self) -> httpx.Client:
        return httpx.Client(base_url=self.base_url, timeout=self.timeout_s)

    def ping(self) -> bool:
        """True if MemVerse HTTP is reachable (OpenAPI /docs or insert probe)."""
        try:
            with self._client() as client:
                r = client.get("/docs")
                if r.status_code == 200:
                    return True
                r2 = client.post("/insert", data={"query": "[agent_ping]"})
                return r2.status_code == 200
        except (httpx.HTTPError, OSError):
            return False

    def write(self, req: MemoryWriteRequest) -> MemoryRecord:
        record_id = str(uuid4())
        payload = encode_envelope(
            device_id=req.device_id,
            category=req.category,
            kind=req.kind,
            record_id=record_id,
            content=req.content.strip(),
        )
        with self._client() as client:
            resp = client.post("/insert", data={"query": payload})
            resp.raise_for_status()
            body = resp.json()
        if body.get("status") != "ok":
            raise RuntimeError(f"MemVerse insert failed: {body}")

        return MemoryRecord(
            record_id=record_id,
            device_id=req.device_id,
            ts=utc_now(),
            category=req.category,
            kind=req.kind,
            content=req.content.strip(),
            content_hash=content_hash(req.content),
            trace_id=req.trace_id,
            source_event_id=req.source_event_id,
            confidence=req.confidence,
            metadata={"memverse_entry": body.get("entry"), **req.metadata},
        )

    def search(self, req: MemorySearchRequest) -> MemorySearchResult:
        query = req.query
        if req.device_id:
            query = f"device {req.device_id}: {query}"
        with self._client() as client:
            resp = client.post(
                "/query",
                data={"query": query, "mode": "hybrid", "use_pm": "false"},
            )
            resp.raise_for_status()
            raw: dict[str, Any] = resp.json()

        if raw.get("status") != "ok":
            raise RuntimeError(f"MemVerse query failed: {raw}")

        hits = _hits_from_query_response(raw, device_id=req.device_id, category=req.category)
        return MemorySearchResult(hits=hits[: req.limit], raw=raw)

    def correct(self, req: MemoryCorrectRequest) -> MemoryRecord:
        tomb_payload = encode_envelope(
            device_id="system",
            category=MemoryCategory.other,
            kind=MemoryKind.note,
            record_id=req.record_id,
            content=f"[tombstone] {req.reason}",
        )
        with self._client() as client:
            client.post("/insert", data={"query": tomb_payload})
        if req.replacement:
            return self.write(req.replacement)
        return MemoryRecord(
            record_id=req.record_id,
            device_id="unknown",
            content=f"[tombstone] {req.reason}",
            status=MemoryStatus.tombstoned,
        )

    def list_records(
        self,
        *,
        device_id: Optional[str] = None,
        category: Optional[MemoryCategory] = None,
        limit: int = 100,
    ) -> list[MemoryRecord]:
        return []


def _hits_from_query_response(
    raw: dict[str, Any],
    *,
    device_id: Optional[str],
    category: Optional[MemoryCategory],
) -> list[MemoryHit]:
    hits: list[MemoryHit] = []
    seen: set[str] = set()

    def _add(hit: MemoryHit) -> None:
        key = f"{hit.record_id}:{hit.content[:80]}"
        if key in seen:
            return
        seen.add(key)
        hits.append(hit)

    for field, score in (("final_answer", 1.0), ("rag_memory", 0.9), ("answer", 1.0), ("response", 0.95)):
        val = raw.get(field)
        if isinstance(val, str) and val.strip() and not _is_error_text(val):
            _add(MemoryHit(record_id=f"memverse-{field}", content=val.strip(), score=score))

    for key in ("context", "chunks", "results", "memories"):
        val = raw.get(key)
        if isinstance(val, list):
            for i, item in enumerate(val):
                text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
                if _is_error_text(text):
                    continue
                parsed = decode_envelope(text) if isinstance(text, str) else None
                if parsed:
                    if device_id and parsed.get("device_id") != device_id:
                        continue
                    cat = parsed.get("category")
                    if category and cat != category.value:
                        continue
                    _add(
                        MemoryHit(
                            record_id=parsed.get("record_id", f"mv-{i}"),
                            content=parsed.get("content", text),
                            device_id=parsed.get("device_id"),
                            category=parse_category(cat) if cat else None,
                            score=0.85,
                        )
                    )
                else:
                    _add(MemoryHit(record_id=f"mv-{i}", content=str(text)[:2000], score=0.5))

    # Envelope snippets embedded in rag text
    rag = raw.get("rag_memory")
    if isinstance(rag, str):
        for m in re.finditer(r"\[agent_memory_v1\][^\n]+", rag):
            parsed = decode_envelope(m.group(0))
            if parsed and parsed.get("content"):
                if device_id and parsed.get("device_id") != device_id:
                    continue
                _add(
                    MemoryHit(
                        record_id=parsed.get("record_id", "mv-rag"),
                        content=parsed["content"],
                        device_id=parsed.get("device_id"),
                        category=parse_category(parsed["category"]) if parsed.get("category") else None,
                        score=0.88,
                    )
                )

    hits.sort(key=lambda h: h.score, reverse=True)
    return hits
