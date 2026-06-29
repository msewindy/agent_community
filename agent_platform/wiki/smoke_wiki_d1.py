#!/usr/bin/env python3
"""M3 D1 smoke — config, contracts export, store skeleton."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.wiki._config import load_wiki_config, resolve_store_root
from agent_platform.wiki.contracts import SCHEMA_VERSION, WikiIngestRequest, write_json_schemas
from agent_platform.wiki.store import ensure_store, layout_for, validate_store


def main() -> int:
    cfg = load_wiki_config()
    root = resolve_store_root(cfg)
    print(f"config store.root -> {root}")

    if cfg.get("store", {}).get("auto_init", True):
        lay = ensure_store(root)
    else:
        lay = layout_for(root)

    missing = validate_store(root)
    if missing:
        print("FAIL: store incomplete:", missing)
        return 1

    with tempfile.TemporaryDirectory() as td:
        tmp = Path(td) / "wiki_test"
        ensure_store(tmp, domain_note="smoke")
        if validate_store(tmp):
            print("FAIL: temp store")
            return 1

    schema_path = Path(__file__).resolve().parent / "schemas" / "wiki_bundle.json"
    write_json_schemas(schema_path)
    req = WikiIngestRequest(source_path="raw/articles/example.md", topic="smoke")
    assert req.trace_id

    print(f"SCHEMA_VERSION={SCHEMA_VERSION}")
    print(f"smoke_wiki_d1: PASS ({lay.root})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
