"""index.md and log.md maintenance (M3 D3)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

from agent_platform.wiki.contracts import WikiPageKind, WikiPageRef, utc_now
from agent_platform.wiki.store import WikiStoreLayout

_PLACEHOLDER = "_(none yet)_"
_SECTION_FOR_KIND: dict[WikiPageKind, str] = {
    WikiPageKind.entity: "Entities",
    WikiPageKind.concept: "Concepts",
    WikiPageKind.synthesis: "Concepts",
    WikiPageKind.comparison: "Comparisons",
    WikiPageKind.archived_query: "Queries",
}

_INDEX_HEADER_DEFAULT = (
    "# Wiki Index\n\n"
    "> Agent-maintained catalog. One line per page. Updated on ingest.\n"
)


@dataclass
class IndexDocument:
    preamble: str = _INDEX_HEADER_DEFAULT
    sections: dict[str, list[str]] = field(default_factory=dict)


def section_name_for_kind(kind: WikiPageKind) -> str:
    return _SECTION_FOR_KIND.get(kind, "Concepts")


def wikilink_target(page_path: str) -> str:
    """Obsidian-style link target from store-relative page path."""
    p = page_path.removesuffix(".md")
    return p


def format_index_entry(page_path: str, title: str, summary: str) -> str:
    link = wikilink_target(page_path)
    one_line = summary.replace("\n", " ").strip()
    if len(one_line) > 200:
        one_line = one_line[:199] + "…"
    return f"- [[{link}|{title}]] — {one_line}"


def _entry_matches_path(line: str, page_path: str) -> bool:
    if page_path in line:
        return True
    link = wikilink_target(page_path)
    return f"[[{link}" in line or f"[[{link}|" in line


def parse_index(content: str) -> IndexDocument:
    doc = IndexDocument()
    if not content.strip():
        doc.sections = {name: [] for name in _SECTION_FOR_KIND.values()}
        return doc

    parts = re.split(r"(?m)^## ", content)
    doc.preamble = parts[0].rstrip() + "\n" if parts else _INDEX_HEADER_DEFAULT
    if len(parts) <= 1:
        doc.sections = {name: [] for name in set(_SECTION_FOR_KIND.values())}
        return doc

    for chunk in parts[1:]:
        lines = chunk.splitlines()
        if not lines:
            continue
        title = lines[0].strip()
        body = [ln for ln in lines[1:] if ln.strip() and ln.strip() != _PLACEHOLDER]
        doc.sections[title] = body
    for name in set(_SECTION_FOR_KIND.values()):
        doc.sections.setdefault(name, [])
    return doc


def _sorted_entries(entries: list[str]) -> list[str]:
    return sorted(entries, key=lambda s: s.lower())


def render_index(doc: IndexDocument) -> str:
    total = sum(len(v) for v in doc.sections.values())
    today = utc_now().strftime("%Y-%m-%d")
    preamble = doc.preamble.rstrip()
    if "Last updated:" in preamble:
        preamble = re.sub(
            r"Last updated: \d{4}-\d{2}-\d{2}",
            f"Last updated: {today}",
            preamble,
        )
    else:
        preamble += f"\n> Last updated: {today} | Total pages: {total}\n"
    if "Total pages:" in preamble:
        preamble = re.sub(r"Total pages: \d+", f"Total pages: {total}", preamble)
    out = [preamble.rstrip(), ""]
    order = ["Entities", "Concepts", "Comparisons", "Queries"]
    for name in order:
        out.append(f"## {name}")
        out.append("")
        entries = doc.sections.get(name, [])
        if entries:
            out.extend(_sorted_entries(entries))
        else:
            out.append(_PLACEHOLDER)
        out.append("")
    return "\n".join(out).rstrip() + "\n"


def upsert_index_entry(
    layout: WikiStoreLayout,
    ref: WikiPageRef,
) -> None:
    """Add or replace one line under the correct index section."""
    path = layout.index_path
    content = path.read_text(encoding="utf-8") if path.is_file() else ""
    doc = parse_index(content)
    section = section_name_for_kind(ref.kind or WikiPageKind.concept)
    entry = format_index_entry(ref.path, ref.title or ref.path, ref.summary)
    lines = doc.sections.get(section, [])
    lines = [ln for ln in lines if not _entry_matches_path(ln, ref.path)]
    lines.append(entry)
    doc.sections[section] = lines
    path.write_text(render_index(doc), encoding="utf-8")


def append_log_entry(
    layout: WikiStoreLayout,
    *,
    action: str,
    subject: str,
    page_path: str,
    raw_rel: str,
    trace_id: str,
    ts: datetime | None = None,
) -> None:
    """Append one ingest line under today's date heading."""
    ts = ts or utc_now()
    date_key = ts.strftime("%Y-%m-%d")
    time_s = ts.strftime("%H:%M:%SZ")
    heading = f"## [{date_key}] {action}"

    path = layout.log_path
    if path.is_file():
        content = path.read_text(encoding="utf-8")
    else:
        content = "# Wiki Log\n\nAppend-only chronicle of ingest/query actions.\n\n"

    line = (
        f"- {time_s} | {subject} | page={page_path} | raw={raw_rel} | trace={trace_id}\n"
    )

    if heading in content:
        idx = content.index(heading)
        next_h = content.find("\n## [", idx + len(heading))
        insert_at = len(content) if next_h == -1 else next_h
        content = content[:insert_at].rstrip() + "\n" + line + content[insert_at:]
    else:
        content = content.rstrip() + "\n\n" + heading + "\n" + line

    path.write_text(content, encoding="utf-8")


def record_ingest(
    layout: WikiStoreLayout,
    ref: WikiPageRef,
    *,
    raw_rel: str,
    trace_id: str,
) -> None:
    """Update index.md and log.md after a successful ingest."""
    upsert_index_entry(layout, ref)
    append_log_entry(
        layout,
        action="ingest",
        subject=ref.title or ref.path,
        page_path=ref.path,
        raw_rel=raw_rel,
        trace_id=trace_id,
    )
