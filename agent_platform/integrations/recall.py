"""M2 + M3 combined recall — memory preferences + wiki topic knowledge (M3 D9)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Optional
from uuid import uuid4

from agent_platform.memory.service import MemoryService
from agent_platform.memory.trace import new_trace_id
from agent_platform.wiki.contracts import WikiQueryRequest
from agent_platform.wiki.service import WikiService

SourceKind = Literal["memory", "wiki"]


@dataclass
class RecallItem:
    source: SourceKind
    title: str
    content: str
    score: float = 0.0
    ref: str = ""


@dataclass
class CombinedRecallResult:
    query: str
    trace_id: str
    memory_items: list[RecallItem] = field(default_factory=list)
    wiki_items: list[RecallItem] = field(default_factory=list)
    prompt_context: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


def _tokenize(query: str) -> list[str]:
    import re

    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
    return [t for t in tokens if len(t) >= 2]


def _memory_items(
    svc: MemoryService,
    query: str,
    limit: int,
    device_id: Optional[str],
    trace_id: str,
) -> list[RecallItem]:
    items: list[RecallItem] = []
    seen: set[str] = set()

    def _collect(search_q: str, boost: float = 1.0) -> None:
        if len(items) >= limit:
            return
        res = svc.search(
            search_q,
            device_id=device_id,
            limit=limit,
            trace_id=trace_id,
        )
        for h in res.hits:
            if h.record_id in seen:
                continue
            seen.add(h.record_id)
            title = (h.category.value if h.category else "memory") + (
                f" / {h.kind.value}" if h.kind else ""
            )
            items.append(
                RecallItem(
                    source="memory",
                    title=title,
                    content=h.content,
                    score=float(h.score or 0.0) * boost,
                    ref=h.record_id,
                )
            )

    _collect(query, 1.0)
    if not items:
        for tok in _tokenize(query):
            _collect(tok, 0.9)
            if items:
                break
    return items[:limit]


def _wiki_items(svc: WikiService, query: str, limit: int, trace_id: str) -> list[RecallItem]:
    res = svc.query(WikiQueryRequest(query=query, limit=limit, trace_id=trace_id))
    items: list[RecallItem] = []
    for h in res.hits:
        body = h.summary or ""
        if res.answer and h.path in res.answer:
            body = (body + " " + res.answer[:400]).strip()
        items.append(
            RecallItem(
                source="wiki",
                title=h.title or h.path,
                content=body or h.path,
                score=float(h.score or 0.0),
                ref=h.path,
            )
        )
    if not items and res.answer:
        items.append(
            RecallItem(
                source="wiki",
                title="wiki synthesis",
                content=res.answer[:800],
                score=0.5,
                ref="wiki/query",
            )
        )
    return items


def format_prompt_context(
    memory_items: list[RecallItem],
    wiki_items: list[RecallItem],
    *,
    max_chars: int = 4000,
) -> str:
    parts: list[str] = []
    if memory_items:
        parts.append("## 用户偏好与事实（记忆层 C1）\n")
        for it in memory_items:
            parts.append(f"- **{it.title}** [{it.ref}]: {it.content[:400]}\n")
    if wiki_items:
        parts.append("\n## 主题知识（Wiki C2）\n")
        for it in wiki_items:
            parts.append(f"- **{it.title}** (`{it.ref}`): {it.content[:500]}\n")
    text = "".join(parts).strip()
    if len(text) > max_chars:
        text = text[: max_chars - 1] + "…"
    return text or "(no recalled context)"


def combined_recall(
    query: str,
    *,
    device_id: Optional[str] = None,
    memory_limit: int = 5,
    wiki_limit: int = 5,
    trace_id: Optional[str] = None,
    memory_service: Optional[MemoryService] = None,
    wiki_service: Optional[WikiService] = None,
) -> CombinedRecallResult:
    """Parallel memory.search + wiki.query, merge for prompt injection."""
    tid = trace_id or new_trace_id()
    mem_svc = memory_service or MemoryService()
    wiki_svc = wiki_service or WikiService()
    device_id = device_id or mem_svc.default_device_id

    memory_items = _memory_items(mem_svc, query, memory_limit, device_id, tid)

    wiki_items = _wiki_items(wiki_svc, query, wiki_limit, tid)
    prompt = format_prompt_context(memory_items, wiki_items)

    return CombinedRecallResult(
        query=query,
        trace_id=tid,
        memory_items=memory_items,
        wiki_items=wiki_items,
        prompt_context=prompt,
        raw={
            "memory_count": len(memory_items),
            "wiki_count": len(wiki_items),
            "device_id": device_id,
        },
    )
