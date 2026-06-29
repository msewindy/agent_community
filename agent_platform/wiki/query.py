"""Wiki query — index-first then ripgrep over compiled pages (M3 D4)."""

from __future__ import annotations

import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from agent_platform.wiki.catalog import (
    append_log_entry,
    parse_index,
    wikilink_target,
)
from agent_platform.wiki.contracts import (
    WikiPageRef,
    WikiQueryRequest,
    WikiQueryResult,
    WikiSearchBackend,
)
from agent_platform.wiki.store import WikiStoreLayout

_SNIPPET_CHARS = 480
_INDEX_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|([^\]]+))?\]\]")


@dataclass
class _ScoredHit:
    path: str
    title: str = ""
    summary: str = ""
    score: float = 0.0
    sources: set[str] = field(default_factory=set)


def tokenize_query(query: str) -> list[str]:
    tokens = re.findall(r"[\w\u4e00-\u9fff]+", query.lower())
    return [t for t in tokens if len(t) >= 2] or [query.lower().strip()]


def _parse_index_line(line: str) -> tuple[str, str, str] | None:
    m = _INDEX_LINK_RE.search(line)
    if not m:
        return None
    link, title_alt = m.group(1), m.group(2)
    rest = line[m.end() :].lstrip("—- ").strip()
    path = link if link.endswith(".md") else f"{link}.md"
    if not path.startswith("wiki/"):
        path = link  # keep as stored in index
    title = (title_alt or "").strip() or Path(path).stem.replace("-", " ").title()
    return path, title, rest


def search_index(layout: WikiStoreLayout, query: str, limit: int) -> list[_ScoredHit]:
    tokens = tokenize_query(query)
    if not layout.index_path.is_file():
        return []
    doc = parse_index(layout.index_path.read_text(encoding="utf-8"))
    hits: list[_ScoredHit] = []
    for entries in doc.sections.values():
        for line in entries:
            low = line.lower()
            score = sum(2.0 for t in tokens if t in low)
            if score <= 0:
                continue
            parsed = _parse_index_line(line)
            if not parsed:
                continue
            path, title, summary = parsed
            hits.append(
                _ScoredHit(
                    path=path,
                    title=title,
                    summary=summary,
                    score=score + 3.0,
                    sources={"index"},
                )
            )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def _ripgrep_paths(wiki_dir: Path, query: str, limit: int) -> list[str]:
    if not wiki_dir.is_dir():
        return []
    rg = shutil.which("rg")
    if not rg:
        return _python_grep_paths(wiki_dir, query, limit)
    try:
        proc = subprocess.run(
            [
                rg,
                "-i",
                "-l",
                "--glob",
                "*.md",
                "--",
                query,
                str(wiki_dir),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return _python_grep_paths(wiki_dir, query, limit)
    if proc.returncode not in (0, 1):
        return _python_grep_paths(wiki_dir, query, limit)
    rels: list[str] = []
    for line in proc.stdout.splitlines():
        p = Path(line.strip())
        try:
            rel = p.resolve().relative_to(wiki_dir.parent.resolve()).as_posix()
        except ValueError:
            rel = p.name
        rels.append(rel)
        if len(rels) >= limit:
            break
    return rels


def _python_grep_paths(wiki_dir: Path, query: str, limit: int) -> list[str]:
    tokens = tokenize_query(query)
    found: list[tuple[float, str]] = []
    for path in wiki_dir.rglob("*.md"):
        try:
            text = path.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        score = sum(1.0 for t in tokens if t in text)
        if score > 0:
            rel = path.resolve().relative_to(wiki_dir.parent.resolve()).as_posix()
            found.append((score, rel))
    found.sort(key=lambda x: x[0], reverse=True)
    return [r for _, r in found[:limit]]


def search_ripgrep(layout: WikiStoreLayout, query: str, limit: int) -> list[_ScoredHit]:
    paths = _ripgrep_paths(layout.wiki_dir, query, limit * 2)
    tokens = tokenize_query(query)
    hits: list[_ScoredHit] = []
    for rel in paths:
        abs_p = layout.root / rel
        if not abs_p.is_file():
            continue
        title, summary = _page_title_summary(abs_p)
        try:
            body = abs_p.read_text(encoding="utf-8").lower()
        except OSError:
            continue
        score = 1.0 + sum(1.5 for t in tokens if t in body)
        hits.append(
            _ScoredHit(
                path=rel,
                title=title,
                summary=summary,
                score=score,
                sources={"ripgrep"},
            )
        )
    hits.sort(key=lambda h: h.score, reverse=True)
    return hits[:limit]


def search_qmd(layout: WikiStoreLayout, query: str, limit: int) -> list[_ScoredHit]:
    """qmd adapter — falls back to ripgrep when qmd is unavailable."""
    qmd = shutil.which("qmd")
    if not qmd:
        hits = search_ripgrep(layout, query, limit)
        for h in hits:
            h.sources.add("qmd_fallback_ripgrep")
        return hits
    try:
        proc = subprocess.run(
            [qmd, "search", query, str(layout.root)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return search_ripgrep(layout, query, limit)
    if proc.returncode != 0 or not proc.stdout.strip():
        return search_ripgrep(layout, query, limit)
    hits: list[_ScoredHit] = []
    for line in proc.stdout.splitlines():
        p = line.strip()
        if not p.endswith(".md"):
            continue
        try:
            rel = Path(p).resolve().relative_to(layout.root.resolve()).as_posix()
        except ValueError:
            if p.startswith("wiki/"):
                rel = p
            else:
                continue
        abs_p = layout.root / rel
        if not abs_p.is_file():
            continue
        title, summary = _page_title_summary(abs_p)
        hits.append(
            _ScoredHit(
                path=rel,
                title=title,
                summary=summary,
                score=2.0,
                sources={"qmd"},
            )
        )
        if len(hits) >= limit:
            break
    return hits


def _page_title_summary(path: Path) -> tuple[str, str]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return path.stem, ""
    title = ""
    if text.startswith("---"):
        end = text.find("\n---", 3)
        if end != -1:
            fm = text[3:end]
            for line in fm.splitlines():
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip()
                    break
    if not title:
        for line in text.splitlines():
            if line.startswith("# "):
                title = line[2:].strip()
                break
    if not title:
        title = path.stem.replace("-", " ").title()
    summary = ""
    for line in text.splitlines():
        s = line.strip()
        if s and not s.startswith("#") and not s.startswith("---"):
            summary = s[:160]
            break
    return title, summary


def _merge_hits(*groups: list[_ScoredHit], limit: int) -> list[_ScoredHit]:
    by_path: dict[str, _ScoredHit] = {}
    for group in groups:
        for h in group:
            if h.path in by_path:
                existing = by_path[h.path]
                existing.score = max(existing.score, h.score) + 0.5
                existing.sources |= h.sources
                if h.summary and not existing.summary:
                    existing.summary = h.summary
            else:
                by_path[h.path] = _ScoredHit(
                    path=h.path,
                    title=h.title,
                    summary=h.summary,
                    score=h.score,
                    sources=set(h.sources),
                )
    merged = sorted(by_path.values(), key=lambda x: x.score, reverse=True)
    return merged[:limit]


def _extract_snippet(path: Path, query: str) -> str:
    tokens = tokenize_query(query)
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    best = ""
    best_score = 0
    for i, line in enumerate(lines):
        low = line.lower()
        score = sum(1 for t in tokens if t in low)
        if score > best_score:
            best_score = score
            chunk = lines[i : i + 6]
            best = "\n".join(chunk).strip()
    if not best:
        best = "\n".join(lines[:8]).strip()
    if len(best) > _SNIPPET_CHARS:
        best = best[: _SNIPPET_CHARS - 1] + "…"
    return best


def build_answer(layout: WikiStoreLayout, query: str, hits: list[WikiPageRef]) -> Optional[str]:
    if not hits:
        return None
    parts = [f"Based on {len(hits)} wiki page(s) for «{query}»:\n"]
    for h in hits[:3]:
        path = layout.root / h.path
        link = wikilink_target(h.path)
        snippet = _extract_snippet(path, query) if path.is_file() else h.summary
        parts.append(f"**[[{link}|{h.title}]]** ({h.path})\n\n{snippet}\n")
    return "\n".join(parts).strip()


def run_query(
    req: WikiQueryRequest,
    layout: WikiStoreLayout,
    *,
    backend: WikiSearchBackend = WikiSearchBackend.ripgrep,
    log_query: bool = True,
) -> WikiQueryResult:
    limit = req.limit
    index_hits = search_index(layout, req.query, limit)
    if backend == WikiSearchBackend.qmd:
        body_hits = search_qmd(layout, req.query, limit)
        backend_name = "qmd"
    else:
        body_hits = search_ripgrep(layout, req.query, limit)
        backend_name = "ripgrep"

    merged = _merge_hits(index_hits, body_hits, limit=limit)
    refs = [
        WikiPageRef(
            path=h.path,
            title=h.title,
            summary=h.summary,
            score=min(h.score / 10.0, 1.0),
        )
        for h in merged
    ]
    answer = build_answer(layout, req.query, refs)
    if log_query:
        trace = req.trace_id or "wiki-query"
        append_log_entry(
            layout,
            action="query",
            subject=req.query[:80],
            page_path=f"hits={len(refs)}",
            raw_rel="-",
            trace_id=trace,
        )
    return WikiQueryResult(
        hits=refs,
        answer=answer,
        raw={
            "backend": backend_name,
            "index_hits": len(index_hits),
            "body_hits": len(body_hits),
        },
    )
