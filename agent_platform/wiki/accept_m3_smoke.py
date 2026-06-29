#!/usr/bin/env python3
"""M3 D5 — automated smoke acceptance (ingest + catalog + query pipeline)."""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from agent_platform.wiki.smoke_wiki import run_smoke


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def main() -> int:
    p = argparse.ArgumentParser(description="M3 smoke acceptance")
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="use project wiki_data (default: isolated temp store)",
    )
    args = p.parse_args()

    if args.root is not None:
        code = run_smoke(args.root.resolve(), trace_id="accept-m3-smoke")
    else:
        with tempfile.TemporaryDirectory(prefix="m3_accept_") as td:
            root = Path(td) / "wiki_store"
            code = run_smoke(root, trace_id="accept-m3-smoke")

    if code != 0:
        _fail("M3 smoke pipeline")
        print("\naccept_m3_smoke: FAIL", file=sys.stderr)
        return 1

    _ok("M3.1 store skeleton")
    _ok("M3.2 ingest → wiki page")
    _ok("M3.3 index.md + log.md")
    _ok("M3.4 query hits + answer")
    print("\naccept_m3_smoke: PASS — M3 D1–D5 pipeline OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
