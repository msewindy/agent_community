#!/usr/bin/env python3
"""M3 D5 — unified wiki smoke: init → ingest → index/log → query."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from agent_platform.wiki._config import load_wiki_config, resolve_store_root
from agent_platform.wiki.contracts import WikiIngestRequest, WikiQueryRequest
from agent_platform.wiki.contracts import write_json_schemas
from agent_platform.wiki.ingest import WikiIngestError
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store, validate_store

_RAW_SAMPLE = """# Agent Community Wiki Smoke

This article describes the LLM Wiki pattern for persistent knowledge.
Keywords: smoke-test-ingest-query.
"""


def _step(name: str) -> None:
    print(f"[wiki-smoke] {name} …", flush=True)


def run_smoke(root: Path | None = None, *, trace_id: str = "wiki-smoke-e2e") -> int:
    cfg = load_wiki_config()
    root = (root or resolve_store_root(cfg)).resolve()

    _step("validate/init store")
    missing = validate_store(root)
    if missing:
        ensure_store(root, domain_note="smoke_wiki")
        missing = validate_store(root)
    if missing:
        print("FAIL store skeleton:", missing, file=sys.stderr)
        return 1

    raw_rel = "raw/articles/smoke-e2e.md"
    raw_path = root / raw_rel
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(_RAW_SAMPLE, encoding="utf-8")

    svc = WikiService(store_root=root)
    _step("ingest")
    try:
        refs = svc.ingest(
            WikiIngestRequest(
                source_path=raw_rel,
                topic="Wiki Smoke E2E",
                trace_id=trace_id,
            )
        )
    except WikiIngestError as e:
        print(f"FAIL ingest: {e}", file=sys.stderr)
        return 1
    if not refs:
        print("FAIL ingest: no pages", file=sys.stderr)
        return 1
    page = root / refs[0].path
    if not page.is_file():
        print(f"FAIL missing page {page}", file=sys.stderr)
        return 1
    print(f"  page={refs[0].path}")

    _step("index + log")
    index = (root / "index.md").read_text(encoding="utf-8")
    log = (root / "log.md").read_text(encoding="utf-8")
    if refs[0].path not in index and "Wiki Smoke" not in index:
        print("FAIL index.md missing entry", file=sys.stderr)
        return 1
    if trace_id not in log or "ingest" not in log:
        print("FAIL log.md missing ingest", file=sys.stderr)
        return 1
    if "Total pages:" not in index:
        print("FAIL index stats header", file=sys.stderr)
        return 1

    _step("query")
    result = svc.query(
        WikiQueryRequest(
            query="LLM Wiki smoke-test-ingest-query",
            limit=5,
            trace_id=trace_id,
        )
    )
    if not result.hits:
        print("FAIL query: no hits", file=sys.stderr)
        return 1
    if not result.answer:
        print("FAIL query: no answer", file=sys.stderr)
        return 1
    if trace_id not in (root / "log.md").read_text(encoding="utf-8"):
        print("FAIL log.md missing query entry", file=sys.stderr)
        return 1
    print(f"  hits={len(result.hits)} top={result.hits[0].path}")

    _step("lint_stub")
    lint = svc.lint_stub()
    if not lint.ok:
        print(f"FAIL lint_stub: {lint.message}", file=sys.stderr)
        return 1

    _step("export schema")
    schema_out = Path(__file__).resolve().parent / "schemas" / "wiki_bundle.json"
    write_json_schemas(schema_out)

    print(f"smoke_wiki: PASS — store={root}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="M3 wiki end-to-end smoke")
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="wiki store root (default: wiki.yaml store.root)",
    )
    p.add_argument(
        "--isolated",
        action="store_true",
        help="use a temp directory (do not touch project wiki_data)",
    )
    p.add_argument("--trace-id", default="wiki-smoke-e2e")
    args = p.parse_args()

    if args.isolated:
        with tempfile.TemporaryDirectory(prefix="wiki_smoke_") as td:
            root = Path(td) / "wiki_store"
            return run_smoke(root, trace_id=args.trace_id)
    return run_smoke(args.root, trace_id=args.trace_id)


if __name__ == "__main__":
    sys.exit(main())
