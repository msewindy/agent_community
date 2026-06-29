#!/usr/bin/env python3
"""M2 D5/D6 — memory_service CLI (write / search / list / gate / audit smoke)."""

from __future__ import annotations

import argparse
import json
import sys

from pathlib import Path

from agent_platform.memory._config import load_memory_config
from agent_platform.memory.contracts import MemoryCategory
from agent_platform.memory.service import MemoryService
from agent_platform.memory.trace import new_trace_id


def _svc(args: argparse.Namespace) -> MemoryService:
    cfg = load_memory_config()
    if getattr(args, "backend", None):
        cfg["backend"] = args.backend
    if getattr(args, "gate", False):
        cfg.setdefault("gate", {})["enabled"] = True
    if getattr(args, "no_gate", False):
        cfg.setdefault("gate", {})["enabled"] = False
    if getattr(args, "audit", False):
        cfg.setdefault("audit", {})["enabled"] = True
    if getattr(args, "audit_db", None):
        cfg.setdefault("audit", {})["db_path"] = args.audit_db
    if getattr(args, "device", None):
        cfg.setdefault("device", {})["default_id"] = args.device
    return MemoryService(config=cfg)


def cmd_write(args: argparse.Namespace) -> int:
    svc = _svc(args)
    cat = MemoryCategory(args.category) if args.category else MemoryCategory.other
    try:
        rec = svc.write(
            args.content,
            device_id=args.device,
            category=cat,
            subject_key=args.subject_key,
            trace_id=args.trace_id,
        )
    except PermissionError as e:
        print(f"REJECTED: {e}", file=sys.stderr)
        return 1
    out = rec.model_dump(mode="json")
    print(json.dumps(out, ensure_ascii=False, indent=2))
    if rec.trace_id:
        print(f"trace_id={rec.trace_id}", file=sys.stderr)
    return 0


def cmd_search(args: argparse.Namespace) -> int:
    svc = _svc(args)
    cat = MemoryCategory(args.category) if args.category else None
    res = svc.search(args.query, device_id=args.device, category=cat, limit=args.limit)
    print(json.dumps(res.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    svc = _svc(args)
    cat = MemoryCategory(args.category) if args.category else None
    rows = svc.list_records(device_id=args.device, category=cat, limit=args.limit)
    print(json.dumps([r.model_dump(mode="json") for r in rows], ensure_ascii=False, indent=2))
    return 0


def cmd_smoke_gate(_: argparse.Namespace) -> int:
    """Demonstrate dedup / conflict / sensitive with gate enabled (mock backend)."""
    cfg = {
        "backend": "mock",
        "device": {"default_id": "cli-gate-smoke"},
        "gate": {
            "enabled": True,
            "dedup": True,
            "conflict_check": True,
            "sensitive_keywords": ["password", "api_key"],
        },
    }
    svc = MemoryService(config=cfg)
    device = "cli-gate-smoke"
    ok = True

    def check(name: str, fn, expect_fail: bool = False) -> None:
        nonlocal ok
        try:
            fn()
            if expect_fail:
                print(f"FAIL {name}: expected rejection", file=sys.stderr)
                ok = False
            else:
                print(f"OK   {name}")
        except PermissionError as e:
            if expect_fail:
                print(f"OK   {name}: rejected ({e})")
            else:
                print(f"FAIL {name}: unexpected rejection {e}", file=sys.stderr)
                ok = False

    check(
        "write_preference",
        lambda: svc.write("用户偏好：简短回复", device_id=device, category=MemoryCategory.preference),
    )
    check(
        "duplicate_blocked",
        lambda: svc.write("用户偏好：简短回复", device_id=device, category=MemoryCategory.preference),
        expect_fail=True,
    )
    check(
        "conflict_first",
        lambda: svc.write(
            "用户偏好：详细展开",
            device_id=device,
            category=MemoryCategory.preference,
            subject_key="user.reply_style",
        ),
    )
    check(
        "conflict_blocked",
        lambda: svc.write(
            "用户偏好：只要一句话",
            device_id=device,
            category=MemoryCategory.preference,
            subject_key="user.reply_style",
        ),
        expect_fail=True,
    )
    check(
        "sensitive_blocked",
        lambda: svc.write("my password is secret", device_id=device),
        expect_fail=True,
    )

    res = svc.search("简短", device_id=device)
    if not res.hits:
        print("FAIL search: no hits", file=sys.stderr)
        ok = False
    else:
        print(f"OK   search hits={len(res.hits)}")

    print("smoke_gate: OK" if ok else "smoke_gate: FAIL")
    return 0 if ok else 1


def cmd_audit(args: argparse.Namespace) -> int:
    svc = _svc(args)
    if not svc.audit_enabled:
        print("audit disabled — use --audit or enable in memory.yaml", file=sys.stderr)
        return 2
    rows = svc.audit_trace(args.trace_id)
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    return 0


def cmd_smoke_audit(args: argparse.Namespace) -> int:
    """Write → gate reject → search under one trace_id; verify audit chain."""
    db = args.audit_db or "/tmp/agent_platform_audit_smoke.db"
    Path(db).unlink(missing_ok=True)
    cfg = {
        "backend": "mock",
        "device": {"default_id": "audit-smoke"},
        "gate": {"enabled": True, "dedup": True},
        "audit": {"enabled": True, "db_path": db},
    }
    svc = MemoryService(config=cfg)
    tid = args.trace_id or "smoke-audit-trace-001"
    device = "audit-smoke"

    rec = svc.write("审计测试：偏好简短", device_id=device, trace_id=tid, category=MemoryCategory.preference)
    try:
        svc.write("审计测试：偏好简短", device_id=device, trace_id=tid, category=MemoryCategory.preference)
    except PermissionError:
        pass
    svc.search("简短", device_id=device, trace_id=tid)

    chain = svc.audit_trace(tid)
    types = [e["event_type"] for e in chain]
    required = ["write_request", "gate_evaluate", "write", "search"]
    ok = all(t in types for t in required)
    rejected = any(e["event_type"] == "gate_evaluate" and e["outcome"] == "rejected" for e in chain)

    print(f"trace_id={tid} events={len(chain)} types={types}")
    if not ok or not rejected:
        print("smoke_audit: FAIL", file=sys.stderr)
        return 1
    print(f"record_id={rec.record_id}")
    print("smoke_audit: OK")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="agent_platform memory CLI")
    p.add_argument("--backend", choices=["mock", "memverse"])
    p.add_argument("--gate", action="store_true", help="enable gate from config override")
    p.add_argument("--no-gate", action="store_true")
    p.add_argument("--device", help="device_id override")
    p.add_argument("--audit", action="store_true", help="enable audit log")
    p.add_argument("--audit-db", dest="audit_db", help="audit sqlite path")

    sub = p.add_subparsers(dest="cmd", required=True)

    w = sub.add_parser("write", help="write memory")
    w.add_argument("content")
    w.add_argument("--category", default="preference")
    w.add_argument("--subject-key", dest="subject_key")
    w.add_argument("--trace-id", dest="trace_id")
    w.set_defaults(func=cmd_write)

    s = sub.add_parser("search", help="search memory")
    s.add_argument("query")
    s.add_argument("--category")
    s.add_argument("--limit", type=int, default=10)
    s.set_defaults(func=cmd_search)

    li = sub.add_parser("list", help="list active records (mock)")
    li.add_argument("--category")
    li.add_argument("--limit", type=int, default=50)
    li.set_defaults(func=cmd_list)

    g = sub.add_parser("smoke-gate", help="run gate MVP smoke (mock)")
    g.set_defaults(func=cmd_smoke_gate)

    a = sub.add_parser("audit", help="list audit events by trace_id")
    a.add_argument("trace_id")
    a.set_defaults(func=cmd_audit)

    sa = sub.add_parser("smoke-audit", help="audit + trace_id smoke (mock)")
    sa.add_argument("--trace-id", dest="trace_id", default=None)
    sa.set_defaults(func=cmd_smoke_audit)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
