#!/usr/bin/env python3
"""M2 D4 — MemVerse end-to-end via memory_service (backend=memverse)."""

from __future__ import annotations

import argparse
import sys

from agent_platform.memory.adapters.memverse import MemVerseAdapter, _is_error_text
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--timeout", type=float, default=180.0)
    args = p.parse_args()

    ad = MemVerseAdapter(args.base_url, timeout_s=args.timeout)
    if not ad.ping():
        print("smoke_memverse_e2e: SKIP — MemVerse not reachable", file=sys.stderr)
        sys.exit(2)

    cfg = {
        "backend": "memverse",
        "memverse": {"base_url": args.base_url, "timeout_s": args.timeout},
        "device": {"default_id": "smoke-memverse"},
        "gate": {"enabled": False},
    }
    svc = MemoryService(adapter=ad, config=cfg)
    marker = "SMOKE_M2_D4"

    rec = svc.write(
        f"{marker}：测试偏好简短回复",
        category=MemoryCategory.preference,
        trace_id="smoke-d4",
    )
    print(f"[memverse] write ok record_id={rec.record_id}")

    res = svc.search(marker, limit=5)
    print(f"[memverse] search hits={len(res.hits)}")
    for h in res.hits[:3]:
        print(f"  - score={h.score:.2f} {h.content[:100]}")

    raw = res.raw or {}
    fa = raw.get("final_answer") or ""
    if _is_error_text(fa):
        print(f"[memverse] WARN final_answer error: {fa[:300]}", file=sys.stderr)
        sys.exit(1)

    print("smoke_memverse_e2e: OK")


if __name__ == "__main__":
    main()
