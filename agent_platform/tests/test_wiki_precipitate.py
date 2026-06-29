"""M3 D6 — precipitate offer tests."""

from __future__ import annotations

import tempfile
from pathlib import Path

from agent_platform.wiki.precipitate import (
    PrecipitateConfig,
    PrecipitateSessionStore,
    evaluate_precipitate,
    is_explicit_command,
    load_precipitate_config,
    write_session_transcript,
)
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store


def test_load_precipitate_config_legacy_ingest_key():
    cfg = load_precipitate_config({"ingest": {"offer_after_turns": 5}})
    assert cfg.offer_after_turns == 5


def test_silent_until_depth():
    store = PrecipitateSessionStore()
    cfg = PrecipitateConfig(offer_after_turns=0, min_assistant_turns=3, min_user_chars_total=50)
    sid = "s1"
    evaluate_precipitate(sid, message="hi", role="user", config=cfg, store=store)
    dec = evaluate_precipitate(sid, message="?", role="assistant", config=cfg, store=store, record=False)
    assert not dec.offer
    assert dec.reason_code in ("insufficient_depth", "silent_mode", "silent")


def test_explicit_command_offers():
    store = PrecipitateSessionStore()
    cfg = PrecipitateConfig(offer_after_turns=0, min_assistant_turns=99)
    dec = evaluate_precipitate(
        "s2", message="/沉淀 MCP", role="user", config=cfg, store=store
    )
    assert dec.offer
    assert dec.reason_code == "explicit_command"


def test_us4_three_assistant_turns(tmp_path: Path):
    store = PrecipitateSessionStore()
    cfg = PrecipitateConfig(
        offer_after_turns=0,
        min_assistant_turns=3,
        min_user_chars_total=30,
        cooldown_turns=5,
    )
    sid = "us4"
    pairs = [
        ("user", "请介绍 MCP 是什么，和 REST 有何不同？"),
        ("assistant", "MCP 是 Model Context Protocol 协议说明…"),
        ("user", "在 Cursor 里怎么配置 MCP server？"),
        ("assistant", "编辑 mcp.json 并启动 server 进程…"),
        ("user", "生产环境有哪些安全最佳实践？"),
        ("assistant", "最小权限、审计调用、密钥管理…"),
    ]
    for role, text in pairs:
        store.record_turn(sid, role, text, topic="MCP")
    dec = evaluate_precipitate(
        sid, message="", role="assistant", config=cfg, store=store, record=False
    )
    assert dec.offer
    assert dec.reason_code == "depth_threshold"


def test_user_acceptance():
    store = PrecipitateSessionStore()
    cfg = PrecipitateConfig()
    dec = evaluate_precipitate("s3", message="好的", role="user", config=cfg, store=store)
    assert dec.offer
    assert dec.reason_code == "user_accepted"


def test_draft_transcript(tmp_path: Path):
    lay = ensure_store(tmp_path / "w")
    msgs = [{"role": "user", "text": "Q"}, {"role": "assistant", "text": "A"}]
    rel = write_session_transcript(lay, "sess-1", msgs, topic="Test")
    assert (tmp_path / "w" / rel).is_file()


def test_wiki_service_precipitate(tmp_path: Path):
    root = tmp_path / "w"
    ensure_store(root)
    svc = WikiService(
        config={
            "store": {"root": str(root), "auto_init": True},
            "precipitate": {"min_assistant_turns": 2, "min_user_chars_total": 10},
        },
        store_root=root,
    )
    svc.record_chat_turn("x", "user", "long question about wiki pattern here")
    svc.record_chat_turn("x", "assistant", "answer one")
    svc.record_chat_turn("x", "user", "follow up question here")
    svc.record_chat_turn("x", "assistant", "answer two")
    dec = svc.evaluate_precipitate_offer("x", record=False)
    assert dec.offer
