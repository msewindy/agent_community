"""Minimal ingest pipeline — one raw file → one wiki page (M3 D2)."""

from __future__ import annotations

import hashlib
import re
from datetime import datetime, timezone
from pathlib import Path

from agent_platform.wiki.catalog import record_ingest
from agent_platform.wiki.contracts import WikiIngestRequest, WikiPageKind, WikiPageRef, utc_now
from agent_platform.wiki.store import WikiStoreLayout

_EXCERPT_CHARS = 4000


class WikiIngestError(ValueError):
    """Invalid ingest input or store state."""


def slugify(text: str) -> str:
    t = text.strip().lower()
    t = re.sub(r"\s+", "-", t)
    t = re.sub(r"[^\w\-\u4e00-\u9fff]", "", t, flags=re.UNICODE)
    return (t[:80].strip("-") or "untitled")


def resolve_raw_path(root: Path, source_path: str) -> tuple[Path, str]:
    """Resolve and validate path under store raw/. Returns (absolute, posix rel from root)."""
    root = root.resolve()
    raw_root = (root / "raw").resolve()
    sp = Path(source_path)
    if sp.is_absolute():
        candidate = sp.resolve()
        try:
            rel = candidate.relative_to(root)
        except ValueError as e:
            raise WikiIngestError(f"source_path must be under store root: {root}") from e
        rel_posix = rel.as_posix()
        if not rel_posix.startswith("raw/"):
            raise WikiIngestError("source_path must be under raw/")
        if not candidate.is_file():
            raise WikiIngestError(f"raw file not found: {candidate}")
        return candidate, rel_posix

    rel = Path(source_path.lstrip("/"))
    rel_posix = rel.as_posix()
    if not rel_posix.startswith("raw/"):
        raise WikiIngestError("source_path must be under raw/ (e.g. raw/articles/note.md)")
    candidate = (root / rel).resolve()
    if not candidate.is_file():
        raise WikiIngestError(f"raw file not found: {candidate}")
    return candidate, rel_posix


def _pick_title(topic: str | None, body: str, slug: str) -> str:
    if topic and topic.strip():
        return topic.strip()
    for line in body.splitlines():
        s = line.strip()
        if s.startswith("# "):
            return s[2:].strip()
        if s.startswith("## "):
            return s[3:].strip()
    return slug.replace("-", " ").title()


def _pick_summary(body: str, max_len: int = 160) -> str:
    lines = body.splitlines()
    buf: list[str] = []
    for line in lines:
        s = line.strip()
        if not s or s.startswith("#"):
            continue
        if s.startswith("---"):
            continue
        buf.append(s)
        joined = " ".join(buf)
        if len(joined) >= 40:
            if len(joined) > max_len:
                return joined[: max_len - 1] + "…"
            return joined
    joined = " ".join(buf).strip()
    return joined[: max_len - 1] + "…" if len(joined) > max_len else joined or "Compiled from raw source."


def _body_excerpt(body: str) -> str:
    text = body.strip()
    if len(text) <= _EXCERPT_CHARS:
        return text
    return text[:_EXCERPT_CHARS] + "\n\n…(truncated)"


def _kind_dir(layout: WikiStoreLayout, kind: WikiPageKind) -> Path:
    if kind == WikiPageKind.entity:
        return layout.entities_dir
    if kind == WikiPageKind.comparison:
        return layout.comparisons_dir
    if kind == WikiPageKind.archived_query:
        return layout.queries_dir
    return layout.concepts_dir


def compile_page_markdown(
    *,
    title: str,
    summary: str,
    raw_rel: str,
    body: str,
    kind: WikiPageKind,
    trace_id: str,
) -> str:
    today = utc_now().strftime("%Y-%m-%d")
    excerpt = _body_excerpt(body)
    return f"""---
title: {title}
created: {today}
updated: {today}
kind: {kind.value}
sources:
  - {raw_rel}
trace_id: {trace_id}
---

# {title}

{summary}

## Compiled excerpt

{excerpt}

## Source

- Raw: `{raw_rel}`
"""


def ingest_one(
    req: WikiIngestRequest,
    layout: WikiStoreLayout,
    *,
    default_kind: WikiPageKind = WikiPageKind.concept,
) -> WikiPageRef:
    """Read one raw file, write wiki page, update index.md and log.md."""
    raw_abs, raw_rel = resolve_raw_path(layout.root, req.source_path)
    body = raw_abs.read_text(encoding="utf-8")
    slug = slugify(req.topic or raw_abs.stem)
    title = _pick_title(req.topic, body, slug)
    summary = _pick_summary(body)
    kind = default_kind
    page_dir = _kind_dir(layout, kind)
    page_dir.mkdir(parents=True, exist_ok=True)
    page_path = page_dir / f"{slug}.md"
    rel_page = page_path.relative_to(layout.root).as_posix()

    content = compile_page_markdown(
        title=title,
        summary=summary,
        raw_rel=raw_rel,
        body=body,
        kind=kind,
        trace_id=req.trace_id,
    )
    page_path.write_text(content, encoding="utf-8")

    ref = WikiPageRef(
        path=rel_page,
        title=title,
        summary=summary,
        kind=kind,
        score=1.0,
    )
    record_ingest(layout, ref, raw_rel=raw_rel, trace_id=req.trace_id)
    return ref


def raw_content_sha256(body: str) -> str:
    return hashlib.sha256(body.encode("utf-8")).hexdigest()
