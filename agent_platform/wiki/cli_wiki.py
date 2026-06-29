#!/usr/bin/env python3
"""Wiki CLI — M3 D1 init / validate."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from agent_platform.wiki._config import resolve_store_root
from agent_platform.wiki.contracts import WikiIngestRequest, WikiQueryRequest
from agent_platform.wiki.ingest import WikiIngestError
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.smoke_wiki import run_smoke
from agent_platform.wiki.store import ensure_store, validate_store
from agent_platform.wiki.contracts import write_json_schemas


def cmd_init(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    lay = ensure_store(root, domain_note=args.domain or "cli init")
    print(f"wiki store: {lay.root}")
    print(f"  SCHEMA  {lay.schema_path}")
    print(f"  index   {lay.index_path}")
    print(f"  log     {lay.log_path}")
    print(f"  raw/    {lay.raw_dir}")
    print(f"  wiki/   {lay.wiki_dir}")
    return 0


def cmd_ingest(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    svc = WikiService(store_root=root)
    try:
        refs = svc.ingest(
            WikiIngestRequest(
                source_path=args.source,
                topic=args.topic,
                trace_id=args.trace_id or None,
            )
        )
    except WikiIngestError as e:
        print(f"wiki ingest: FAIL — {e}")
        return 1
    for r in refs:
        print(f"wiki ingest: OK {r.path} — {r.title}")
    return 0


def cmd_query(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    svc = WikiService(store_root=root)
    result = svc.query(
        WikiQueryRequest(
            query=args.query,
            limit=args.limit,
            trace_id=args.trace_id,
        )
    )
    print(f"wiki query: {len(result.hits)} hit(s)")
    for h in result.hits:
        print(f"  [{h.score:.2f}] {h.path} — {h.title}")
    if result.answer:
        print()
        print(result.answer)
    return 0


def cmd_precipitate(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    svc = WikiService(store_root=root)
    dec = svc.evaluate_precipitate_offer(
        args.session,
        message=args.text or "",
        role=args.role,
        topic=args.topic,
        record=not args.no_record,
    )
    print(f"wiki precipitate: offer={dec.offer} reason={dec.reason_code}")
    if dec.message:
        print(f"  message: {dec.message}")
    if dec.details:
        print(f"  details: {dec.details}")
    return 0


def cmd_precipitate_record(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    svc = WikiService(store_root=root)
    svc.record_chat_turn(args.session, args.role, args.text, topic=args.topic)
    print(f"wiki precipitate-record: session={args.session} role={args.role}")
    return 0


def cmd_precipitate_simulate(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    svc = WikiService(store_root=root)
    sid = args.session
    topic = args.topic or "MCP"
    prompts = [
        ("user", "MCP 是什么？和 LSP 有什么区别？"),
        ("assistant", "MCP 是 Model Context Protocol，用于连接 LLM 与工具…"),
        ("user", "那 Cursor 里怎么用 MCP server？"),
        ("assistant", "在 Cursor 中配置 mcp.json 并启动 server…"),
        ("user", "有没有安全方面的最佳实践？"),
        ("assistant", "建议最小权限、审计调用、不要明文放密钥…"),
    ]
    for role, text in prompts:
        svc.record_chat_turn(sid, role, text, topic=topic)
    dec = svc.evaluate_precipitate_offer(sid, message="", role="assistant", record=False)
    print(f"wiki precipitate-simulate: offer={dec.offer} reason={dec.reason_code}")
    if dec.offer:
        print(f"  message: {dec.message}")
    return 0 if dec.offer else 1


def cmd_smoke(args: argparse.Namespace) -> int:
    return run_smoke(args.root, trace_id=args.trace_id or "cli-smoke")


def cmd_export_schema(args: argparse.Namespace) -> int:
    out = args.output
    write_json_schemas(out)
    print(f"wiki export-schema: wrote {out}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    root = resolve_store_root() if args.root is None else args.root
    missing = validate_store(root)
    if missing:
        print("wiki validate: FAIL")
        for m in missing:
            print(f"  missing: {m}")
        return 1
    print(f"wiki validate: OK ({root})")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="agent_platform wiki CLI")
    sub = p.add_subparsers(dest="cmd", required=True)

    init_p = sub.add_parser("init", help="create wiki_data skeleton")
    init_p.add_argument("--root", type=Path, default=None)
    init_p.add_argument("--domain", type=str, default=None)
    init_p.set_defaults(func=cmd_init)

    ing_p = sub.add_parser("ingest", help="ingest one raw file → one wiki page (D2)")
    ing_p.add_argument("source", help="path under raw/, e.g. raw/articles/note.md")
    ing_p.add_argument("--topic", type=str, default=None)
    ing_p.add_argument("--trace-id", type=str, default=None)
    ing_p.add_argument("--root", type=Path, default=None)
    ing_p.set_defaults(func=cmd_ingest)

    q_p = sub.add_parser("query", help="search index + wiki pages (D4)")
    q_p.add_argument("query", help="search string")
    q_p.add_argument("--limit", type=int, default=8)
    q_p.add_argument("--trace-id", type=str, default=None)
    q_p.add_argument("--root", type=Path, default=None)
    q_p.set_defaults(func=cmd_query)

    prec_p = sub.add_parser("precipitate", help="evaluate ingest offer (D6)")
    prec_p.add_argument("--session", default="cli-session", help="chat session id")
    prec_p.add_argument("--text", type=str, default="")
    prec_p.add_argument("--role", choices=("user", "assistant", "system"), default="user")
    prec_p.add_argument("--topic", type=str, default=None)
    prec_p.add_argument("--root", type=Path, default=None)
    prec_p.add_argument("--no-record", action="store_true")
    prec_p.set_defaults(func=cmd_precipitate)

    prec_rec = sub.add_parser("precipitate-record", help="record one chat turn (D6)")
    prec_rec.add_argument("--session", default="cli-session")
    prec_rec.add_argument("--role", choices=("user", "assistant", "system"), required=True)
    prec_rec.add_argument("--text", required=True)
    prec_rec.add_argument("--topic", type=str, default=None)
    prec_rec.add_argument("--root", type=Path, default=None)
    prec_rec.set_defaults(func=cmd_precipitate_record)

    prec_sim = sub.add_parser("precipitate-simulate", help="US-4 depth → offer demo (D6)")
    prec_sim.add_argument("--session", default="simulate-us4")
    prec_sim.add_argument("--topic", default="MCP")
    prec_sim.add_argument("--root", type=Path, default=None)
    prec_sim.set_defaults(func=cmd_precipitate_simulate)

    smk_p = sub.add_parser("smoke", help="end-to-end smoke (D5)")
    smk_p.add_argument("--root", type=Path, default=None)
    smk_p.add_argument("--trace-id", type=str, default=None)
    smk_p.set_defaults(func=cmd_smoke)

    exp_p = sub.add_parser("export-schema", help="write JSON schema bundle")
    exp_p.add_argument(
        "-o",
        "--output",
        type=Path,
        default=Path(__file__).resolve().parent / "schemas" / "wiki_bundle.json",
    )
    exp_p.set_defaults(func=cmd_export_schema)

    val_p = sub.add_parser("validate", help="check required paths exist")
    val_p.add_argument("--root", type=Path, default=None)
    val_p.set_defaults(func=cmd_validate)

    args = p.parse_args()
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
