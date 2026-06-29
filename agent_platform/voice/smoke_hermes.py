#!/usr/bin/env python3
"""M1 D6: Hermes bridge smoke (non-interactive -q -Q)."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_ROOT))

from voice._config import load_voice_config  # noqa: E402
from voice.hermes_bridge import HermesBridge  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("-q", "--query", default="用一句话介绍你自己，中文。")
    args = parser.parse_args()
    cfg = load_voice_config()["hermes"]
    bridge = HermesBridge(
        provider=cfg.get("provider", "deepseek"),
        model=cfg.get("model", "deepseek-chat"),
    )
    reply = bridge.ask(args.query)
    print(f"session_id: {reply.session_id}")
    print(f"elapsed_ms: {reply.elapsed_ms:.0f}")
    print(f"reply:\n{reply.text}")
    return 0 if reply.text else 1


if __name__ == "__main__":
    raise SystemExit(main())
