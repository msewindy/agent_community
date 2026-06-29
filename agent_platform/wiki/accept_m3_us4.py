#!/usr/bin/env python3
"""M3 D8 — automated acceptance for US-4 (knowledge precipitate → wiki → recall)."""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path

from agent_platform.wiki.contracts import WikiIngestRequest, WikiQueryRequest
from agent_platform.wiki.service import WikiService


def _ok(msg: str) -> None:
    print(f"OK   {msg}")


def _fail(msg: str) -> None:
    print(f"FAIL {msg}", file=sys.stderr)


def _wiki_cfg(root: Path) -> dict:
    return {
        "store": {"root": str(root), "auto_init": True},
        "precipitate": {
            "enabled": True,
            "offer_after_turns": 0,
            "min_assistant_turns": 3,
            "min_user_chars_total": 80,
            "min_user_chars_per_turn": 15,
            "cooldown_turns": 10,
        },
        "search": {"backend": "ripgrep", "limit_default": 8},
    }


def _simulate_mcp_dialogue(svc: WikiService, session_id: str) -> str:
    """US-4: three rounds of deep Q&A on MCP."""
    topic = "MCP"
    turns = [
        ("user", "请详细解释 MCP（Model Context Protocol）是什么，和 LSP 有什么本质区别？"),
        (
            "assistant",
            "MCP 是连接 LLM 应用与外部工具/数据的标准协议；LSP 面向编辑器语言服务…",
        ),
        ("user", "在 Cursor 里如何配置 MCP server？需要哪些权限和安全注意点？"),
        (
            "assistant",
            "在 Cursor 中通过 mcp.json 声明 server；注意最小权限与密钥管理…",
        ),
        ("user", "MCP 与 REST API 集成相比，架构上有什么优缺点？"),
        (
            "assistant",
            "MCP 提供结构化工具发现与会话上下文；REST 更通用但缺少标准工具契约…",
        ),
    ]
    for role, text in turns:
        svc.record_chat_turn(session_id, role, text, topic=topic)
    return topic


def accept_us4_precipitate_offer(svc: WikiService, session_id: str) -> bool:
    dec = svc.evaluate_precipitate_offer(session_id, role="assistant", record=False)
    if not dec.offer or dec.reason_code != "depth_threshold":
        _fail(f"US-4 precipitate offer: offer={dec.offer} reason={dec.reason_code}")
        return False
    _ok(f"US-4 after 3 answers → offer precipitate ({dec.reason_code})")
    return True


def accept_us4_user_accept_and_ingest(
    svc: WikiService, session_id: str, topic: str, root: Path
) -> str | None:
    dec = svc.evaluate_precipitate_offer(
        session_id, message="好的，沉淀吧", role="user", record=False
    )
    if not dec.offer:
        _fail(f"US-4 user acceptance: {dec.reason_code}")
        return None
    _ok("US-4 user says 好 → ready for ingest")

    raw_rel = svc.draft_transcript_for_ingest(session_id, topic=topic)
    raw_path = root / raw_rel
    if not raw_path.is_file():
        _fail(f"US-4 transcript missing: {raw_rel}")
        return None
    _ok(f"US-4 transcript → {raw_rel}")

    refs = svc.ingest(
        WikiIngestRequest(
            source_path=raw_rel,
            topic=topic,
            trace_id="us4-accept-ingest",
        )
    )
    if not refs:
        _fail("US-4 ingest returned no pages")
        return None
    page_rel = refs[0].path
    page_path = root / page_rel
    if not page_path.is_file():
        _fail(f"US-4 wiki page missing: {page_rel}")
        return None
    _ok(f"US-4 ingest → {page_rel}")

    index = (root / "index.md").read_text(encoding="utf-8")
    log = (root / "log.md").read_text(encoding="utf-8")
    if page_rel not in index and topic.upper() not in index.upper():
        _fail("US-4 index.md missing page entry")
        return None
    if "us4-accept-ingest" not in log:
        _fail("US-4 log.md missing ingest entry")
        return None
    _ok("US-4 index.md + log.md updated")
    return page_rel


def accept_us4_next_day_recall(root: Path, page_rel: str, topic: str) -> bool:
    """Simulate next session: new WikiService, query should hit compiled wiki."""
    svc2 = WikiService(config=_wiki_cfg(root), store_root=root)
    res = svc2.query(
        WikiQueryRequest(
            query=f"{topic} Cursor 配置与安全",
            limit=5,
            trace_id="us4-day2-query",
        )
    )
    if not res.hits:
        _fail(f"US-4 day-2 query: no hits (expected {page_rel})")
        return False
    paths = [h.path for h in res.hits]
    if page_rel not in paths and not any("mcp" in p.lower() for p in paths):
        _fail(f"US-4 day-2 query hits wrong pages: {paths}")
        return False
    if not res.answer or topic.upper() not in res.answer.upper() and "MCP" not in res.answer:
        _fail("US-4 day-2 query: answer missing compiled content")
        return False
    _ok(f"US-4 day-2 query hits={len(res.hits)} (wiki compounding)")
    return True


def accept_us4_hermes_tools(root: Path) -> bool:
    try:
        from agent_platform.integrations.hermes import wiki_tools as wt
        from agent_platform.integrations.hermes.tools import bootstrap_agent_platform
    except ImportError as e:
        _fail(f"US-4 hermes tools import: {e}")
        return False

    bootstrap_agent_platform()
    cfg = _wiki_cfg(root)
    svc = WikiService(config=cfg, store_root=root)
    wt._get_wiki_service = lambda: svc  # type: ignore[attr-defined]

    raw = root / "raw" / "articles" / "hermes-us4.md"
    raw.parent.mkdir(parents=True, exist_ok=True)
    raw.write_text(
        "# Hermes US4\n\nHermes tool path for wiki acceptance.\n",
        encoding="utf-8",
    )

    ing = json.loads(
        wt.wiki_ingest(
            {"source_path": "raw/articles/hermes-us4.md", "topic": "Hermes US4"},
            current_session_id="us4-hermes",
        )
    )
    if not ing.get("success"):
        _fail(f"US-4 wiki_ingest tool: {ing}")
        return False

    svc2 = WikiService(config=cfg, store_root=root)
    wt._get_wiki_service = lambda: svc2  # type: ignore[attr-defined]
    q = json.loads(wt.wiki_query({"query": "Hermes US4 acceptance"}, current_session_id="us4-hermes-2"))
    if not q.get("success") or not q.get("count"):
        _fail(f"US-4 wiki_query tool after restart: {q}")
        return False
    _ok("US-4 Hermes wiki_ingest → restart → wiki_query")
    return True


def accept_us4_full(root: Path) -> bool:
    session_id = "us4-acceptance-session"
    svc = WikiService(config=_wiki_cfg(root), store_root=root)
    topic = _simulate_mcp_dialogue(svc, session_id)
    if not accept_us4_precipitate_offer(svc, session_id):
        return False
    page_rel = accept_us4_user_accept_and_ingest(svc, session_id, topic, root)
    if not page_rel:
        return False
    return accept_us4_next_day_recall(root, page_rel, topic)


def main() -> int:
    p = argparse.ArgumentParser(description="M3 US-4 acceptance (D8)")
    p.add_argument(
        "--root",
        type=Path,
        default=None,
        help="use persistent wiki store (default: temp dir)",
    )
    p.add_argument("--skip-hermes", action="store_true")
    args = p.parse_args()

    ok = True
    if args.root is not None:
        root = args.root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        if not accept_us4_full(root):
            ok = False
        if not args.skip_hermes and not accept_us4_hermes_tools(root):
            ok = False
    else:
        with tempfile.TemporaryDirectory(prefix="m3_us4_") as td:
            root = Path(td) / "wiki_store"
            if not accept_us4_full(root):
                ok = False
            if not args.skip_hermes and not accept_us4_hermes_tools(root):
                ok = False

    print()
    if ok:
        print("accept_m3_us4: PASS — US-4 automated checks OK")
        print(
            "Manual (recommended): hermes chat → 3 deep MCP questions → accept沉淀 → "
            "next day ask again with wiki_query"
        )
        return 0
    print("accept_m3_us4: FAIL", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())
