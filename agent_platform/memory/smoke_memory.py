#!/usr/bin/env python3
"""M2 D1 smoke: Mock adapter + optional MemVerse HTTP."""

from __future__ import annotations

import argparse
import sys

import httpx

from agent_platform.memory.adapters.mock import MockMemAdapter
from agent_platform.memory.contracts import MemoryCategory, MemoryCorrectRequest, MemoryWriteRequest
from agent_platform.memory.service import MemoryService


def smoke_mock() -> None:
    svc = MemoryService(adapter=MockMemAdapter())
    device = "smoke-device"
    r1 = svc.write("用户偏好：回复尽量简短", device_id=device, category=MemoryCategory.preference)
    print(f"[mock] write ok record_id={r1.record_id}")
    res = svc.search("简短", device_id=device)
    print(f"[mock] search hits={len(res.hits)}")
    for h in res.hits:
        print(f"  - {h.content[:80]}")
    if not res.hits:
        raise SystemExit("mock search returned no hits")

    svc.correct(
        MemoryCorrectRequest(
            record_id=r1.record_id,
            reason="test tombstone",
            replacement=MemoryWriteRequest(
                content="用户偏好：可以用列表",
                device_id=device,
                category=MemoryCategory.preference,
            ),
        )
    )
    res2 = svc.search("简短", device_id=device)
    if any("尽量简短" in h.content for h in res2.hits):
        raise SystemExit("tombstoned record still searchable")
    print("[mock] correct + search ok")


def smoke_memverse(base_url: str, timeout_s: float) -> None:
    print(f"[memverse] probing {base_url} ...")
    with httpx.Client(base_url=base_url, timeout=timeout_s) as client:
        resp = client.post("/insert", data={"query": "M2 D1 smoke: hello MemVerse"})
        print(f"[memverse] insert status={resp.status_code} body={resp.text[:500]}")
        resp.raise_for_status()
        q = client.post("/query", data={"query": "M2 D1 smoke", "mode": "hybrid"})
        print(f"[memverse] query status={q.status_code} body={q.text[:800]}")
        q.raise_for_status()


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--memverse", action="store_true", help="also hit MemVerse /insert /query")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--timeout", type=float, default=180.0)
    args = p.parse_args()

    smoke_mock()
    if args.memverse:
        smoke_memverse(args.base_url, args.timeout)
    print("smoke_memory: OK")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"smoke_memory: FAIL — {e}", file=sys.stderr)
        raise
