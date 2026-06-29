#!/usr/bin/env python3
"""M3 D6 smoke — precipitate offer: silent, explicit /沉淀, US-4 depth."""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

from agent_platform.wiki.precipitate import (
    PrecipitateConfig,
    PrecipitateSessionStore,
    evaluate_precipitate,
    is_explicit_command,
)
from agent_platform.wiki.service import WikiService
from agent_platform.wiki.store import ensure_store


def main() -> int:
    with tempfile.TemporaryDirectory() as td:
        root = Path(td) / "wiki"
        ensure_store(root)

        cfg_silent = PrecipitateConfig(offer_after_turns=0, min_assistant_turns=3)
        store = PrecipitateSessionStore()
        sid = "smoke-d6"

        dec = evaluate_precipitate(
            sid, message="随便聊聊", role="user", config=cfg_silent, store=store
        )
        if dec.offer:
            print("FAIL: should be silent on turn 1", file=sys.stderr)
            return 1

        if not is_explicit_command("/沉淀 到 wiki", cfg_silent.explicit_commands):
            print("FAIL: explicit command detect", file=sys.stderr)
            return 1

        dec_ex = evaluate_precipitate(
            sid,
            message="/沉淀",
            role="user",
            config=cfg_silent,
            store=PrecipitateSessionStore(),
        )
        if not dec_ex.offer or dec_ex.reason_code != "explicit_command":
            print("FAIL: explicit /沉淀 should offer", file=sys.stderr)
            return 1

        svc = WikiService(
            config={
                "store": {"root": str(root), "auto_init": True},
                "precipitate": {
                    "enabled": True,
                    "offer_after_turns": 0,
                    "min_assistant_turns": 3,
                    "min_user_chars_total": 20,
                },
            },
            store_root=root,
        )
        topic = "MCP"
        for role, text in [
            ("user", "请详细解释 MCP 架构是什么，和 LSP 有什么区别？"),
            ("assistant", "MCP 是 Model Context Protocol，用于连接 LLM 与外部工具…"),
            ("user", "在 Cursor 里如何配置 MCP server？需要哪些权限？"),
            ("assistant", "在 Cursor 中编辑 mcp.json 并启动 server 进程…"),
            ("user", "MCP 部署时有哪些安全最佳实践值得遵守？"),
            ("assistant", "建议最小权限、审计调用、不要明文存放密钥…"),
        ]:
            svc.record_chat_turn("us4", role, text, topic=topic)

        dec_us4 = svc.evaluate_precipitate_offer("us4", role="assistant", record=False)
        if not dec_us4.offer:
            print(f"FAIL US-4 depth offer: {dec_us4.reason_code}", file=sys.stderr)
            return 1

        raw = svc.draft_transcript_for_ingest("us4", topic=topic)
        if not (root / raw).is_file():
            print(f"FAIL transcript {raw}", file=sys.stderr)
            return 1

        print(f"smoke_wiki_d6: PASS offer={dec_us4.reason_code} transcript={raw}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
